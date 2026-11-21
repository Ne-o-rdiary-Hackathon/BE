"""빙고판 생성 · 조회 · 사진 인증(빙고 판정) · 결과.

칸 위치(position)는 0~8, 왼쪽 위부터 행 순서입니다.
    0 1 2
    3 4 5
    6 7 8
score = 그 활동을 '하고 싶어요'로 고른 인원 - '질렸어요'로 고른 인원 (제출 완료한 설문만 집계)
"""
import random
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common import BusinessException, ErrorCode
from app.db.base import now_kst
from app.models.activity import Activity, ResponseStatus, SelectionType, UserResponse, UserResponseActivity
from app.models.bingo import BingoBoard, BingoCell, CellStatus, Verification
from app.models.room import Room, RoomMember, RoomStatus
from app.models.user import User
from app.schemas.bingo import (
    BingoBoardResponse,
    BoardMemberResponse,
    BingoCellResponse,
    BingoResultResponse,
    ResultMemberResponse,
    VerificationResponse,
)
from app.services.image_storage import ImageStorage, detect_image_type

BOARD_SIZE = 3
CELL_COUNT = BOARD_SIZE * BOARD_SIZE
CENTER = 4
MAX_RESETS = 1  # 방장이 빙고판을 다시 돌릴 수 있는 횟수
LINES: tuple[tuple[int, int, int], ...] = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # 가로
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # 세로
    (0, 4, 8), (2, 4, 6),             # 대각선
)

_rng = random.Random()


def completed_lines(completed_positions: set[int]) -> list[tuple[int, int, int]]:
    return [line for line in LINES if all(p in completed_positions for p in line)]


def _positions_in(lines: list[tuple[int, int, int]]) -> set[int]:
    return {p for line in lines for p in line}


def _ids_at(cells: list[BingoCell], positions: set[int]) -> list[int]:
    return [c.cell_id for c in sorted(cells, key=lambda c: c.position) if c.position in positions]


class BingoService:
    def __init__(self, db: Session, storage: ImageStorage):
        self.db = db
        self.storage = storage

    # ───────────────────────── BINGO-01 빙고판 생성 ─────────────────────────

    def create_board(self, room_id: int, user: User) -> BingoBoardResponse:
        try:
            room = self._lock_room(room_id)
            self._ensure_member(room_id, user)
            if room.owner_id != user.user_id:
                raise BusinessException(ErrorCode.NOT_ROOM_OWNER)
            if self._find_board(room_id) is not None:
                raise BusinessException(ErrorCode.BOARD_ALREADY_EXISTS)
            if room.status != RoomStatus.RECRUITING:
                raise BusinessException(ErrorCode.ROOM_NOT_RECRUITING)

            votes = self._activity_votes(room_id)
            board = BingoBoard(room_id=room_id, board_size=BOARD_SIZE)
            self.db.add(board)
            self.db.flush()
            self._fill_cells(board, room_id, votes, exclude=set())
            room.status = RoomStatus.IN_PROGRESS
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise BusinessException(ErrorCode.BOARD_ALREADY_EXISTS) from None
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(board)
        return self._board_response(room, board, votes, user)

    # ───────────────────────── BINGO-03 빙고판 다시 돌리기 (방장, 1회) ─────────────────────────

    def reset_board(self, room_id: int, user: User) -> BingoBoardResponse:
        try:
            room = self._lock_room(room_id)
            self._ensure_member(room_id, user)
            if room.owner_id != user.user_id:
                raise BusinessException(ErrorCode.NOT_ROOM_OWNER)
            board = self.db.scalar(
                select(BingoBoard)
                .where(BingoBoard.room_id == room_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if board is None:
                raise BusinessException(ErrorCode.BOARD_NOT_FOUND)
            if room.status != RoomStatus.IN_PROGRESS:
                raise BusinessException(ErrorCode.ROOM_NOT_IN_PROGRESS)
            if board.reset_count >= MAX_RESETS:
                raise BusinessException(ErrorCode.RESET_LIMIT_EXCEEDED)

            cells = list(self.db.scalars(
                select(BingoCell)
                .where(BingoCell.board_id == board.board_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).unique())
            if any(c.status == CellStatus.COMPLETED for c in cells):
                raise BusinessException(ErrorCode.RESET_AFTER_VERIFICATION)

            # 지금 칸의 활동은 최대한 빼고 새로 뽑습니다.
            previous = {c.activity_id for c in cells}
            for cell in cells:
                self.db.delete(cell)
            self.db.flush()

            votes = self._activity_votes(room_id)
            self._fill_cells(board, room_id, votes, exclude=previous)
            board.reset_count += 1
            board.generated_at = now_kst()
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(board)
        return self._board_response(room, board, votes, user)

    def _fill_cells(
        self, board: BingoBoard, room_id: int, votes: dict[int, tuple[int, int]], exclude: set[int]
    ) -> None:
        chosen = self._choose_activities(votes, exclude)
        member_count = self.db.scalar(
            select(func.count()).select_from(RoomMember).where(RoomMember.room_id == room_id)
        ) or 1

        # 점수 1위 활동은 가운데, 나머지는 무작위 위치
        others = [p for p in range(CELL_COUNT) if p != CENTER]
        _rng.shuffle(others)
        positions = [CENTER, *others]

        for activity, position in zip(chosen, positions):
            desired, _ = votes.get(activity.activity_id, (0, 0))
            rate = min(Decimal(desired * 100) / Decimal(member_count), Decimal(100))
            self.db.add(BingoCell(
                board_id=board.board_id,
                activity_id=activity.activity_id,
                position=position,
                match_rate=rate.quantize(Decimal("0.01")),
                status=CellStatus.PENDING,
            ))
        self.db.flush()

    def _choose_activities(self, votes: dict[int, tuple[int, int]], exclude: set[int]) -> list[Activity]:
        activities = list(self.db.scalars(select(Activity).where(Activity.is_active.is_(True))))
        if len(activities) < CELL_COUNT:
            raise BusinessException(ErrorCode.NOT_ENOUGH_ACTIVITIES)

        def rank(activity: Activity):
            desired, bored = votes.get(activity.activity_id, (0, 0))
            # 제외 대상은 맨 뒤 → 점수 높은 순 → 하고 싶은 사람 많은 순 → 같으면 무작위
            return activity.activity_id in exclude, -(desired - bored), -desired, _rng.random()

        return sorted(activities, key=rank)[:CELL_COUNT]

    # ───────────────────────── BINGO-02 빙고판 조회 ─────────────────────────

    def get_board(self, room_id: int, user: User) -> BingoBoardResponse:
        room = self._get_room(room_id)
        self._ensure_member(room_id, user)
        board = self._get_board(room_id)
        return self._board_response(room, board, self._activity_votes(room_id), user)

    # ───────────────────────── VERIFY-01 사진 인증 ─────────────────────────

    def verify_cell(self, room_id: int, cell_id: int, user: User, image: bytes) -> VerificationResponse:
        # 1) 잠금 없이 먼저 검사 (실패할 요청이면 사진을 올리지 않음)
        room = self._get_room(room_id)
        self._ensure_member(room_id, user)
        if room.status != RoomStatus.IN_PROGRESS:
            raise BusinessException(ErrorCode.ROOM_NOT_IN_PROGRESS)
        board = self._get_board(room_id)
        cell = next((c for c in board.cells if c.cell_id == cell_id), None)
        if cell is None:
            raise BusinessException(ErrorCode.CELL_NOT_FOUND)
        if cell.status == CellStatus.COMPLETED:
            raise BusinessException(ErrorCode.CELL_ALREADY_COMPLETED)

        ext, content_type = detect_image_type(image)
        image_key = f"verifications/{room_id}/{cell_id}/{uuid4().hex}.{ext}"

        # 2) 사진 업로드 (DB 잠금을 잡기 전에 해서 다른 멤버 인증을 막지 않음)
        self.storage.save(image_key, image, content_type)

        # 3) 방을 잠그고 최신 상태로 다시 확인한 뒤 저장 + 빙고 판정
        try:
            room = self._lock_room(room_id)
            if room.status != RoomStatus.IN_PROGRESS:
                raise BusinessException(ErrorCode.ROOM_NOT_IN_PROGRESS)
            cells = list(self.db.scalars(
                select(BingoCell)
                .where(BingoCell.board_id == board.board_id)
                .order_by(BingoCell.position)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).unique())
            cell = next(c for c in cells if c.cell_id == cell_id)
            if cell.status == CellStatus.COMPLETED:
                raise BusinessException(ErrorCode.CELL_ALREADY_COMPLETED)

            before = {c.position for c in cells if c.status == CellStatus.COMPLETED}
            lines_before = completed_lines(before)

            now = now_kst()
            cell.status = CellStatus.COMPLETED
            cell.completed_at = now
            cell.verification = Verification(cell_id=cell.cell_id, user_id=user.user_id, image_key=image_key)

            after = before | {cell.position}
            lines_after = completed_lines(after)
            new_lines = [line for line in lines_after if line not in lines_before]

            room_completed = len(lines_after) >= room.target_bingo
            if room_completed:
                room.status = RoomStatus.COMPLETED
                room.completed_at = now
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            self.storage.delete(image_key)
            raise BusinessException(ErrorCode.CELL_ALREADY_COMPLETED) from None
        except Exception:
            self.db.rollback()
            self.storage.delete(image_key)
            raise

        votes = self._activity_votes(room_id)
        return VerificationResponse(
            cell=self._cell_response(cell, votes),
            achieved_bingo=len(lines_after),
            completed_cells=len(after),
            new_bingo_cell_ids=_ids_at(cells, _positions_in(new_lines)),
            bingo_cell_ids=_ids_at(cells, _positions_in(lines_after)),
            room_completed=room_completed,
        )

    # ───────────────────────── RESULT-01 결과 조회 ─────────────────────────

    def get_result(self, room_id: int, user: User) -> BingoResultResponse:
        room = self._get_room(room_id)
        self._ensure_member(room_id, user)
        board = self._get_board(room_id)
        votes = self._activity_votes(room_id)

        done = {c.position for c in board.cells if c.status == CellStatus.COMPLETED}
        lines = completed_lines(done)

        counts = dict(self.db.execute(
            select(Verification.user_id, func.count())
            .join(BingoCell, BingoCell.cell_id == Verification.cell_id)
            .where(BingoCell.board_id == board.board_id)
            .group_by(Verification.user_id)
        ).all())
        members = self.db.scalars(
            select(RoomMember).where(RoomMember.room_id == room_id).order_by(RoomMember.joined_at)
        ).unique()

        return BingoResultResponse(
            room_name=room.room_name,
            target_bingo=room.target_bingo,
            achieved_bingo=len(lines),
            completed_cells=len(done),
            bingo_cell_ids=_ids_at(board.cells, _positions_in(lines)),
            members=[
                ResultMemberResponse(
                    nickname=m.user.nickname,
                    profile_image_url=m.user.profile_image_url,
                    verified_count=counts.get(m.user_id, 0),
                )
                for m in members
            ],
            cells=[self._cell_response(c, votes) for c in board.cells],
        )

    # ───────────────────────── 내부 함수 ─────────────────────────

    def _get_room(self, room_id: int) -> Room:
        room = self.db.get(Room, room_id)
        if room is None:
            raise BusinessException(ErrorCode.ROOM_NOT_FOUND)
        return room

    def _lock_room(self, room_id: int) -> Room:
        """같은 방의 생성/인증 요청을 한 번에 하나씩 처리하도록 방 행을 잠급니다."""
        room = self.db.scalar(
            select(Room)
            .where(Room.room_id == room_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if room is None:
            raise BusinessException(ErrorCode.ROOM_NOT_FOUND)
        return room

    def _ensure_member(self, room_id: int, user: User) -> None:
        exists = self.db.scalar(
            select(RoomMember.room_member_id)
            .where(RoomMember.room_id == room_id, RoomMember.user_id == user.user_id)
        )
        if exists is None:
            raise BusinessException(ErrorCode.NOT_ROOM_MEMBER)

    def _find_board(self, room_id: int) -> BingoBoard | None:
        return self.db.scalar(select(BingoBoard).where(BingoBoard.room_id == room_id))

    def _get_board(self, room_id: int) -> BingoBoard:
        board = self._find_board(room_id)
        if board is None:
            raise BusinessException(ErrorCode.BOARD_NOT_FOUND)
        return board

    def _activity_votes(self, room_id: int) -> dict[int, tuple[int, int]]:
        """활동별 (하고 싶어요 수, 질렸어요 수). 제출 완료한 설문만 셉니다."""
        desired = func.sum(case((UserResponseActivity.selection_type == SelectionType.DESIRED, 1), else_=0))
        bored = func.sum(case((UserResponseActivity.selection_type == SelectionType.BORED, 1), else_=0))
        rows = self.db.execute(
            select(UserResponseActivity.activity_id, desired, bored)
            .join(UserResponse, UserResponse.response_id == UserResponseActivity.response_id)
            .where(UserResponse.room_id == room_id, UserResponse.status == ResponseStatus.SUBMITTED)
            .group_by(UserResponseActivity.activity_id)
        ).all()
        return {activity_id: (int(d or 0), int(b or 0)) for activity_id, d, b in rows}

    def _cell_response(self, cell: BingoCell, votes: dict[int, tuple[int, int]]) -> BingoCellResponse:
        desired, bored = votes.get(cell.activity_id, (0, 0))
        return BingoCellResponse(
            cell_id=cell.cell_id,
            position=cell.position,
            activity_name=cell.activity.activity_name,
            score=desired - bored,
            status=cell.status,
            image_url=self.storage.url(cell.verification.image_key) if cell.verification else None,
        )

    def _board_response(
        self, room: Room, board: BingoBoard, votes: dict[int, tuple[int, int]], user: User
    ) -> BingoBoardResponse:
        done = {c.position for c in board.cells if c.status == CellStatus.COMPLETED}
        lines = completed_lines(done)
        members = self.db.scalars(
            select(RoomMember).where(RoomMember.room_id == room.room_id).order_by(RoomMember.joined_at)
        ).unique()
        return BingoBoardResponse(
            room_name=room.room_name,
            is_owner=room.owner_id == user.user_id,
            reset_remaining=max(MAX_RESETS - board.reset_count, 0),
            members=[
                BoardMemberResponse(
                    user_id=m.user_id,
                    nickname=m.user.nickname,
                    profile_image_url=m.user.profile_image_url,
                    role=m.role,
                )
                for m in members
            ],
            room_status=room.status,
            target_bingo=room.target_bingo,
            achieved_bingo=len(lines),
            completed_cells=len(done),
            bingo_cell_ids=_ids_at(board.cells, _positions_in(lines)),
            cells=[self._cell_response(c, votes) for c in board.cells],
        )
