#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable


class TransactionState(Enum):
    ACTIVE = "active"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"


class DatabaseError(Exception):
    """Base exception for database architecture simulation errors."""


class ConstraintViolation(DatabaseError):
    pass


class TransactionError(DatabaseError):
    pass


@dataclass(frozen=True)
class User:
    user_id: int
    username: str


@dataclass
class Account:
    account_id: int
    owner_id: int
    balance_cents: int
    version: int = 0


@dataclass(frozen=True)
class AuditEntry:
    event: str
    details: str
    created_at: datetime


class InMemoryDatabase:
    """
    Small relational-database simulation.

    The implementation separates:
    - normalized entities: users and accounts
    - uniqueness validation
    - transaction state
    - commit/rollback behavior
    - optimistic version checks
    - audit logging
    """

    def __init__(self) -> None:
        self.users: dict[int, User] = {}
        self.accounts: dict[int, Account] = {}
        self.audit_log: list[AuditEntry] = []
        self._next_user_id = 1
        self._next_account_id = 1

    def add_user(self, username: str) -> User:
        username = username.strip()
        if not username:
            raise ConstraintViolation("Username cannot be empty.")

        if any(user.username.casefold() == username.casefold()
               for user in self.users.values()):
            raise ConstraintViolation("Username must be unique.")

        user = User(self._next_user_id, username)
        self.users[user.user_id] = user
        self._next_user_id += 1
        return user

    def add_account(self, owner_id: int, opening_balance_cents: int = 0) -> Account:
        if owner_id not in self.users:
            raise ConstraintViolation("Account owner does not exist.")
        if opening_balance_cents < 0:
            raise ConstraintViolation("Opening balance cannot be negative.")

        account = Account(
            account_id=self._next_account_id,
            owner_id=owner_id,
            balance_cents=opening_balance_cents,
        )
        self.accounts[account.account_id] = account
        self._next_account_id += 1
        return account

    def get_account(self, account_id: int) -> Account:
        try:
            return self.accounts[account_id]
        except KeyError as exc:
            raise ConstraintViolation("Account does not exist.") from exc

    def record_audit(self, event: str, details: str) -> None:
        self.audit_log.append(
            AuditEntry(
                event=event,
                details=details,
                created_at=datetime.now(timezone.utc),
            )
        )


class Transaction:
    """
    Snapshot-based transaction.

    Changes remain isolated from the database until commit.
    A failed operation can be rolled back without partially changing
    persistent state.
    """

    def __init__(self, database: InMemoryDatabase) -> None:
        self.database = database
        self.state = TransactionState.ACTIVE
        self._accounts: dict[int, Account] = {
            account_id: Account(
                account.account_id,
                account.owner_id,
                account.balance_cents,
                account.version,
            )
            for account_id, account in database.accounts.items()
        }
        self._original_versions = {
            account_id: account.version
            for account_id, account in database.accounts.items()
        }

    def _require_active(self) -> None:
        if self.state is not TransactionState.ACTIVE:
            raise TransactionError("Transaction is no longer active.")

    def transfer(
        self,
        source_id: int,
        destination_id: int,
        amount_cents: int,
    ) -> None:
        self._require_active()

        if source_id == destination_id:
            raise ConstraintViolation("Source and destination must differ.")
        if amount_cents <= 0:
            raise ConstraintViolation("Transfer amount must be positive.")

        if source_id not in self._accounts or destination_id not in self._accounts:
            raise ConstraintViolation("Both accounts must exist.")

        source = self._accounts[source_id]
        destination = self._accounts[destination_id]

        if source.balance_cents < amount_cents:
            raise ConstraintViolation("Insufficient funds.")

        source.balance_cents -= amount_cents
        destination.balance_cents += amount_cents

    def commit(self) -> None:
        self._require_active()

        # Optimistic concurrency check prevents overwriting a newer update.
        for account_id, original_version in self._original_versions.items():
            current = self.database.accounts.get(account_id)
            if current is None:
                raise TransactionError("Account disappeared during transaction.")
            if current.version != original_version:
                raise TransactionError(
                    f"Concurrent modification detected for account {account_id}."
                )

        changed = False
        for account_id, staged in self._accounts.items():
            current = self.database.accounts[account_id]
            if (
                current.balance_cents != staged.balance_cents
                or current.version != staged.version
            ):
                current.balance_cents = staged.balance_cents
                current.version += 1
                changed = True

        self.state = TransactionState.COMMITTED

        if changed:
            self.database.record_audit(
                "transaction_commit",
                "Account balances committed atomically.",
            )

    def rollback(self) -> None:
        self._require_active()
        self.state = TransactionState.ROLLED_BACK
        self.database.record_audit(
            "transaction_rollback",
            "Transaction changes discarded.",
        )


def demonstrate_normalization(database: InMemoryDatabase) -> None:
    """
    Demonstrates normalized storage:
    user information is stored once and referenced by accounts.
    """

    alice = database.add_user("alice")
    bob = database.add_user("bob")

    database.add_account(alice.user_id, 100_00)
    database.add_account(bob.user_id, 25_00)

    print("Normalized entities:")
    for user in database.users.values():
        print(f"  User {user.user_id}: {user.username}")

    for account in database.accounts.values():
        print(
            f"  Account {account.account_id}: "
            f"owner_id={account.owner_id}, "
            f"balance={account.balance_cents / 100:.2f}"
        )


def demonstrate_transaction(database: InMemoryDatabase) -> None:
    print("\nSuccessful transaction:")
    transaction = Transaction(database)
    transaction.transfer(1, 2, 20_00)
    transaction.commit()

    for account in database.accounts.values():
        print(
            f"  Account {account.account_id}: "
            f"{account.balance_cents / 100:.2f}"
        )

    print("\nFailed transaction with rollback:")
    transaction = Transaction(database)
    try:
        transaction.transfer(1, 2, 10_000_00)
        transaction.commit()
    except DatabaseError as exc:
        transaction.rollback()
        print(f"  Rejected: {exc}")

    print("\nBalances after rollback:")
    for account in database.accounts.values():
        print(
            f"  Account {account.account_id}: "
            f"{account.balance_cents / 100:.2f}"
        )


def demonstrate_constraint_validation(database: InMemoryDatabase) -> None:
    print("\nConstraint validation:")

    try:
        database.add_user("ALICE")
    except ConstraintViolation as exc:
        print(f"  Duplicate username rejected: {exc}")

    try:
        database.add_account(999, 100)
    except ConstraintViolation as exc:
        print(f"  Invalid foreign key rejected: {exc}")

    try:
        database.add_account(1, -1)
    except ConstraintViolation as exc:
        print(f"  Invalid balance rejected: {exc}")


def demonstrate_file_export(database: InMemoryDatabase) -> None:
    """
    Standard-library file handling provides a simple operational audit export.
    """
    path = Path("database_audit.txt")
    with path.open("w", encoding="utf-8") as file:
        for entry in database.audit_log:
            file.write(
                f"{entry.created_at.isoformat()} | "
                f"{entry.event} | {entry.details}\n"
            )

    print(f"\nAudit log written to {path.resolve()}")


def run_assertions(database: InMemoryDatabase) -> None:
    total = sum(account.balance_cents for account in database.accounts.values())
    assert total == 12_500, "Transaction conservation invariant failed."
    assert database.accounts[1].balance_cents == 80_00
    assert database.accounts[2].balance_cents == 45_00

    assert all(account.balance_cents >= 0
               for account in database.accounts.values())


def main() -> None:
    database = InMemoryDatabase()

    demonstrate_normalization(database)
    demonstrate_transaction(database)
    demonstrate_constraint_validation(database)
    run_assertions(database)
    demonstrate_file_export(database)

    print("\nDatabase architecture simulation completed.")
    print(
        f"Users={len(database.users)}, "
        f"Accounts={len(database.accounts)}, "
        f"AuditEvents={len(database.audit_log)}"
    )


if __name__ == "__main__":
    main()
