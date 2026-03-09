"""
Seed script: creates an admin user and optionally a test team.
Usage: docker compose exec api python -m app.scripts.seed
"""
import asyncio
import sys

from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
from app.models.models import Team, User


async def seed():
    async with AsyncSessionLocal() as db:
        # Admin user
        result = await db.execute(select(User).where(User.email == "admin@agile.local"))
        if not result.scalar_one_or_none():
            user = User(
                email="admin@agile.local",
                name="Admin",
                surname="User",
                hashed_password=get_password_hash("admin123"),
                role="admin",
            )
            db.add(user)
            print("✅ Created admin user: admin@agile.local / admin123")
        else:
            print("ℹ️  Admin user already exists")

        # Example team (optional — requires real Jira project key)
        project_key = sys.argv[1] if len(sys.argv) > 1 else None
        if project_key:
            result2 = await db.execute(
                select(Team).where(Team.jira_project_key == project_key)
            )
            if not result2.scalar_one_or_none():
                team = Team(
                    name=f"Team {project_key}",
                    jira_project_key=project_key,
                )
                db.add(team)
                print(f"✅ Created team for project: {project_key}")

        await db.commit()
        print("✅ Seed complete")


if __name__ == "__main__":
    asyncio.run(seed())
