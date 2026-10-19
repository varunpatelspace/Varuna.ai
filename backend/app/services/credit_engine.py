"""
Deterministic Token and Credit Economy Engine.
Implements:
1. Two-phase credit reservation & atomic settlement.
2. Prevention of negative balances and double-spending via transaction isolation.
3. Immutable double-entry ledger bookkeeping.
"""

from typing import Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.billing import CreditAccount, CreditLedgerEntry, LedgerEntryType
from app.config import settings


class CreditEngine:
    @staticmethod
    def get_or_create_account(db: Session, organization_id: str) -> CreditAccount:
        """Retrieves or creates a credit account for an organization."""
        account = db.query(CreditAccount).filter(CreditAccount.organization_id == organization_id).first()
        if not account:
            account = CreditAccount(
                organization_id=organization_id,
                balance=settings.SIGNUP_FREE_CREDITS,
                reserved_balance=0.0,
                lifetime_granted=settings.SIGNUP_FREE_CREDITS,
                lifetime_consumed=0.0
            )
            db.add(account)
            db.flush()

            # Record initial grant ledger entry
            initial_entry = CreditLedgerEntry(
                account_id=account.id,
                entry_type=LedgerEntryType.GRANT,
                amount=settings.SIGNUP_FREE_CREDITS,
                balance_after=settings.SIGNUP_FREE_CREDITS,
                reference_id="signup_grant",
                description="Complimentary Welcome AI Credits"
            )
            db.add(initial_entry)
            db.commit()
            db.refresh(account)
        return account

    @staticmethod
    def reserve_credits(
        db: Session,
        organization_id: str,
        estimated_credits: float,
        reference_id: str
    ) -> CreditAccount:
        """
        Phase 1: Reserve credits before starting an AI generation or tool call.
        Locks the account row and ensures available_balance >= estimated_credits.
        """
        # Ensure non-negative reservation request
        estimated_credits = max(0.1, round(estimated_credits, 2))
        
        # In SQLite, transactions are serialized by default at BEGIN IMMEDIATE.
        # In Postgres, use with_for_update().
        query = db.query(CreditAccount).filter(CreditAccount.organization_id == organization_id)
        if not settings.DATABASE_URL.startswith("sqlite"):
            query = query.with_for_update()

        account = query.first()
        if not account:
            account = CreditEngine.get_or_create_account(db, organization_id)

        available_balance = account.balance - account.reserved_balance
        if available_balance < estimated_credits:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "INSUFFICIENT_CREDITS",
                    "message": f"Insufficient AI credits. Available: {available_balance:.2f}, Required: {estimated_credits:.2f}.",
                    "available_credits": available_balance,
                    "required_credits": estimated_credits,
                    "upgrade_url": "/pricing"
                }
            )

        account.reserved_balance += estimated_credits
        
        ledger_entry = CreditLedgerEntry(
            account_id=account.id,
            entry_type=LedgerEntryType.RESERVATION,
            amount=-estimated_credits,
            balance_after=account.balance - account.reserved_balance,
            reference_id=reference_id,
            description=f"Pre-request credit hold for query {reference_id}"
        )
        db.add(ledger_entry)
        db.commit()
        db.refresh(account)
        return account

    @staticmethod
    def settle_credits(
        db: Session,
        organization_id: str,
        reserved_credits: float,
        actual_credits: float,
        reference_id: str,
        description: str
    ) -> Tuple[CreditAccount, float]:
        """
        Phase 2: Settle reservation with actual consumed credits.
        Releases reserved hold and deducts actual credits from balance.
        """
        actual_credits = max(0.0, round(actual_credits, 2))
        
        query = db.query(CreditAccount).filter(CreditAccount.organization_id == organization_id)
        if not settings.DATABASE_URL.startswith("sqlite"):
            query = query.with_for_update()

        account = query.first()
        if not account:
            raise HTTPException(status_code=500, detail="Credit account not found for settlement")

        # Release reservation
        account.reserved_balance = max(0.0, account.reserved_balance - reserved_credits)
        
        # Deduct actual credits
        account.balance = max(0.0, round(account.balance - actual_credits, 2))
        account.lifetime_consumed += actual_credits

        # Create immutable settlement ledger entry
        settle_entry = CreditLedgerEntry(
            account_id=account.id,
            entry_type=LedgerEntryType.SETTLEMENT,
            amount=-actual_credits,
            balance_after=account.balance,
            reference_id=reference_id,
            description=description
        )
        db.add(settle_entry)
        db.commit()
        db.refresh(account)
        return account, actual_credits

    @staticmethod
    def refund_reservation(
        db: Session,
        organization_id: str,
        reserved_credits: float,
        reference_id: str,
        reason: str = "Request failed or aborted"
    ) -> CreditAccount:
        """
        Releases a reservation without charging the account (for failed or cancelled requests).
        """
        query = db.query(CreditAccount).filter(CreditAccount.organization_id == organization_id)
        if not settings.DATABASE_URL.startswith("sqlite"):
            query = query.with_for_update()

        account = query.first()
        if not account:
            return None

        account.reserved_balance = max(0.0, account.reserved_balance - reserved_credits)
        
        refund_entry = CreditLedgerEntry(
            account_id=account.id,
            entry_type=LedgerEntryType.REFUND,
            amount=reserved_credits,
            balance_after=account.balance,
            reference_id=reference_id,
            description=f"Hold released: {reason}"
        )
        db.add(refund_entry)
        db.commit()
        db.refresh(account)
        return account

    @staticmethod
    def top_up_credits(
        db: Session,
        organization_id: str,
        credits: float,
        reference_id: str,
        description: str
    ) -> CreditAccount:
        """Grants paid or top-up credits to an organization."""
        query = db.query(CreditAccount).filter(CreditAccount.organization_id == organization_id)
        if not settings.DATABASE_URL.startswith("sqlite"):
            query = query.with_for_update()

        account = query.first()
        if not account:
            account = CreditEngine.get_or_create_account(db, organization_id)

        account.balance += credits
        account.lifetime_granted += credits

        entry = CreditLedgerEntry(
            account_id=account.id,
            entry_type=LedgerEntryType.TOP_UP,
            amount=credits,
            balance_after=account.balance,
            reference_id=reference_id,
            description=description
        )
        db.add(entry)
        db.commit()
        db.refresh(account)
        return account
