# app/cli.py
import argparse
import sys

from sqlmodel import Session, select

from app.core.database import create_db_and_tables, engine
from app.core.security import hash_password
from app.models.user import User


def create_admin(args):
    create_db_and_tables()
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == args.username)).first()
        if existing:
            print(f"Error: user '{args.username}' already exists.")
            sys.exit(1)
        user = User(
            username=args.username,
            email=args.email,
            hashed_password=hash_password(args.password),
            is_admin=True,
        )
        session.add(user)
        session.commit()
        print(f"Admin user '{args.username}' created successfully.")


def main():
    parser = argparse.ArgumentParser(prog="proxyhub-cli", description="ProxyHub CLI")
    subparsers = parser.add_subparsers(dest="command")

    admin_parser = subparsers.add_parser("create-admin", help="Create an admin user")
    admin_parser.add_argument("--username", required=True)
    admin_parser.add_argument("--email", default=None)
    admin_parser.add_argument("--password", required=True)

    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
