"""Seed demo data: one merchant wired to the service wallet.

Usage:
  python scripts/seed.py --owner +254712345678 --name "Mama Njeri's Shop"
  # optionally pre-create a demo invoice:
  python scripts/seed.py --owner +254712345678 --name "Mama Njeri's Shop" \
      --customer +254798765432 --customer-name John --amount 50 --desc delivery
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import chain  # noqa: E402
from app.db import Invoice, Merchant, get_session, init_db  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--owner", required=True, help="Owner WhatsApp number, E.164 (+2547…)")
    p.add_argument("--name", default="Demo Shop", help="Business name")
    p.add_argument("--wallet", default=None, help="Merchant wallet (default: service wallet)")
    p.add_argument("--customer", default=None, help="Optional customer WhatsApp number")
    p.add_argument("--customer-name", default="John")
    p.add_argument("--amount", type=float, default=50.0)
    p.add_argument("--desc", default="delivery")
    args = p.parse_args()

    init_db()
    wallet = args.wallet or chain.get_service_wallet()

    with get_session() as db:
        merchant = db.execute(
            select(Merchant).where(Merchant.whatsapp_number == args.owner)
        ).scalar_one_or_none()
        if merchant:
            merchant.business_name = args.name
            merchant.wallet_address = wallet
            print(f"Updated merchant #{merchant.id}: {args.name} ({args.owner})")
        else:
            merchant = Merchant(
                whatsapp_number=args.owner, business_name=args.name, wallet_address=wallet
            )
            db.add(merchant)
            db.flush()
            print(f"Created merchant #{merchant.id}: {args.name} ({args.owner})")
        print(f"  wallet: {wallet}")

        if args.customer:
            invoice = Invoice(
                merchant_id=merchant.id,
                customer_name=args.customer_name,
                customer_whatsapp=args.customer,
                amount_cusd=args.amount,
                description=args.desc,
                status="pending",
                payment_address=wallet,
                due_at=datetime.utcnow() + timedelta(days=3),
            )
            db.add(invoice)
            db.flush()
            print(f"Created invoice #{invoice.id}: {args.amount} cUSD for {args.customer_name}")
            print(f"  payment page: /pay/{invoice.id}")


if __name__ == "__main__":
    main()
