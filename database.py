"""Асинхронный слой работы с базой данных SQLite через SQLAlchemy 2.0."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс для декларативных моделей."""


class User(Base):
    """Таблица пользователей Telegram."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    appointments: Mapped[list["Appointment"]] = relationship(back_populates="user")


class Appointment(Base):
    """Таблица записей на услуги."""

    __tablename__ = "appointments"
    __table_args__ = (
        UniqueConstraint("appointment_time", name="uq_appointments_appointment_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    service: Mapped[str] = mapped_column(String(255))
    appointment_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="appointments")


class Database:
    """Класс-обёртка над SQLAlchemy AsyncEngine и часто используемыми запросами."""

    def __init__(self, database_url: str):
        self.engine = create_async_engine(database_url, echo=False, future=True)
        self.session_factory = async_sessionmaker(
            bind=self.engine, expire_on_commit=False, class_=AsyncSession
        )

    async def create_tables(self) -> None:
        """Создаёт таблицы при первом запуске."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def upsert_user(self, user_id: int, username: str | None, full_name: str) -> None:
        """Создаёт пользователя при первом входе или обновляет имя/username."""
        async with self.session_factory() as session:
            existing_user = await session.get(User, user_id)
            if existing_user:
                existing_user.username = username
                existing_user.full_name = full_name
            else:
                session.add(User(id=user_id, username=username, full_name=full_name))
            await session.commit()

    async def is_slot_free(self, appointment_time: datetime) -> bool:
        """Проверяет, свободен ли слот времени (только для активных записей)."""
        async with self.session_factory() as session:
            stmt = select(Appointment).where(
                Appointment.appointment_time == appointment_time,
                Appointment.status == "active",
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is None

    async def create_appointment(
        self, user_id: int, service: str, appointment_time: datetime
    ) -> Appointment | None:
        """
        Создаёт запись, если слот ещё свободен.

        Возвращает объект записи при успехе, иначе None.
        """
        async with self.session_factory() as session:
            stmt = select(Appointment).where(
                Appointment.appointment_time == appointment_time,
                Appointment.status == "active",
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                return None

            appointment = Appointment(
                user_id=user_id,
                service=service,
                appointment_time=appointment_time,
                status="active",
            )
            session.add(appointment)
            await session.commit()
            await session.refresh(appointment)
            return appointment

    async def has_user_active_appointment(self, user_id: int) -> bool:
        """Проверяет, есть ли у пользователя хотя бы одна активная запись."""
        async with self.session_factory() as session:
            stmt = select(Appointment.id).where(
                Appointment.user_id == user_id, Appointment.status == "active"
            )
            result = await session.execute(stmt)
            return result.first() is not None

    async def get_user_active_appointments(self, user_id: int) -> Sequence[Appointment]:
        """Возвращает активные записи конкретного пользователя."""
        async with self.session_factory() as session:
            stmt = (
                select(Appointment)
                .where(Appointment.user_id == user_id, Appointment.status == "active")
                .order_by(Appointment.appointment_time.asc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_appointment_by_id(self, appointment_id: int) -> Appointment | None:
        """Получает запись по ID."""
        async with self.session_factory() as session:
            stmt = select(Appointment).where(Appointment.id == appointment_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def cancel_appointment(self, appointment_id: int) -> bool:
        """Меняет статус записи на cancelled."""
        async with self.session_factory() as session:
            appointment = await session.get(Appointment, appointment_id)
            if not appointment or appointment.status != "active":
                return False
            appointment.status = "cancelled"
            await session.commit()
            return True

    async def get_appointments_by_date(self, date_start: datetime, date_end: datetime) -> Sequence[Appointment]:
        """Возвращает все записи в выбранный день (любого статуса)."""
        async with self.session_factory() as session:
            stmt = (
                select(Appointment)
                .where(
                    Appointment.appointment_time >= date_start,
                    Appointment.appointment_time < date_end,
                )
                .order_by(Appointment.appointment_time.asc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def delete_appointment(self, appointment_id: int) -> bool:
        """Удаляет запись полностью из базы (админ-действие)."""
        async with self.session_factory() as session:
            appointment = await session.get(Appointment, appointment_id)
            if not appointment:
                return False
            await session.delete(appointment)
            await session.commit()
            return True

    async def get_taken_slots(self, date_start: datetime, date_end: datetime) -> set[datetime]:
        """Возвращает занятые активные слоты за выбранный день."""
        async with self.session_factory() as session:
            stmt = select(Appointment.appointment_time).where(
                Appointment.appointment_time >= date_start,
                Appointment.appointment_time < date_end,
                Appointment.status == "active",
            )
            result = await session.execute(stmt)
            return set(result.scalars().all())

    async def mark_past_appointments_completed(self, now_dt: datetime) -> int:
        """
        Переводит прошедшие активные записи в статус completed.

        Возвращает количество обновлённых строк.
        """
        async with self.session_factory() as session:
            stmt = (
                update(Appointment)
                .where(
                    Appointment.status == "active",
                    Appointment.appointment_time < now_dt,
                )
                .values(status="completed")
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount or 0
