import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import aiosqlite
from src.utils.config_loader import AppConfig
import structlog

logger = structlog.get_logger(__name__)

class KnowledgeStore:
    """
    Handles all SQLite read/write operations for the slow-changing, 
    human-curated knowledge database (topics, jobs, testimonials, calendar weights).
    """
    def __init__(self, config: AppConfig):
        self.config = config.storage
        self.db_path = Path(self.config.knowledge_database_path)
        self.seed_dir = Path(self.config.seed_data_dir)
        self.schema_path = Path(__file__).parent / "schema_knowledge.sql"

    async def initialize(self):
        """Ensure database directory exists, run DDL schema script, and import seed data."""
        # Ensure data folder exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info("Initializing Knowledge Store", db_path=str(self.db_path))
        
        async with aiosqlite.connect(self.db_path) as conn:
            # Enable foreign keys
            await conn.execute("PRAGMA foreign_keys = ON;")
            
            # Read and execute schema
            schema_ddl = self.schema_path.read_text(encoding="utf-8")
            await conn.executescript(schema_ddl)
            await conn.commit()
            
            # Seed if empty
            await self._seed_if_empty(conn)

    async def _seed_if_empty(self, conn: aiosqlite.Connection):
        """Seed tables from JSON files if they contain 0 rows."""
        # 1. Calendar Config
        async with conn.execute("SELECT COUNT(*) FROM calendar_config") as cursor:
            row = await cursor.fetchone()
            if row[0] == 0:
                await self._seed_calendar(conn)

        # 2. Topics Bank
        async with conn.execute("SELECT COUNT(*) FROM topics_bank") as cursor:
            row = await cursor.fetchone()
            if row[0] == 0:
                await self._seed_topics(conn)

        # 3. Jobs Sheet
        async with conn.execute("SELECT COUNT(*) FROM jobs_sheet") as cursor:
            row = await cursor.fetchone()
            if row[0] == 0:
                await self._seed_jobs(conn)

        # 4. Testimonials
        async with conn.execute("SELECT COUNT(*) FROM testimonials") as cursor:
            row = await cursor.fetchone()
            if row[0] == 0:
                await self._seed_testimonials(conn)

    async def _seed_calendar(self, conn: aiosqlite.Connection):
        path = self.seed_dir / "calendar_config.json"
        if not path.exists():
            return
        logger.info("Seeding calendar config...")
        items = json.loads(path.read_text(encoding="utf-8"))
        for item in items:
            await conn.execute(
                "INSERT INTO calendar_config (pillar, target_weight, description) VALUES (?, ?, ?)",
                (item["pillar"], item["target_weight"], item["description"])
            )
        await conn.commit()

    async def _seed_topics(self, conn: aiosqlite.Connection):
        path = self.seed_dir / "topics_bank.json"
        if not path.exists():
            return
        logger.info("Seeding topics bank...")
        items = json.loads(path.read_text(encoding="utf-8"))
        for item in items:
            await conn.execute(
                """INSERT INTO topics_bank (topic_id, pillar, topic_title, topic_context, suggested_template) 
                   VALUES (?, ?, ?, ?, ?)""",
                (item["topic_id"], item["pillar"], item["topic_title"], item["topic_context"], item["suggested_template"])
            )
        await conn.commit()

    async def _seed_jobs(self, conn: aiosqlite.Connection):
        path = self.seed_dir / "jobs_sheet.json"
        if not path.exists():
            return
        logger.info("Seeding jobs sheet...")
        items = json.loads(path.read_text(encoding="utf-8"))
        for item in items:
            await conn.execute(
                """INSERT INTO jobs_sheet (job_id, company, role, location, link, posted_date, featured) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (item["job_id"], item["company"], item["role"], item["location"], item["link"], item["posted_date"], 1 if item["featured"] else 0)
            )
        await conn.commit()

    async def _seed_testimonials(self, conn: aiosqlite.Connection):
        path = self.seed_dir / "testimonials.json"
        if not path.exists():
            return
        logger.info("Seeding testimonials...")
        items = json.loads(path.read_text(encoding="utf-8"))
        for item in items:
            await conn.execute(
                """INSERT INTO testimonials (testimonial_id, name, quote, role_landed, photo_path) 
                   VALUES (?, ?, ?, ?, ?)""",
                (item["testimonial_id"], item["name"], item["quote"], item["role_landed"], item["photo_path"])
            )
        await conn.commit()

    # ── Database Queries ──

    async def get_available_topics(self, pillar: str) -> List[Dict[str, Any]]:
        """Fetch all active topics for a specific pillar that haven't been marked as used."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM topics_bank WHERE pillar = ? AND used = 0", (pillar,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_topic_by_id(self, topic_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific topic's details by its ID."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM topics_bank WHERE topic_id = ?", (topic_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_featured_jobs(self) -> List[Dict[str, Any]]:
        """Fetch all featured jobs that are active."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM jobs_sheet WHERE featured = 1 ORDER BY posted_date DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_random_testimonial(self) -> Optional[Dict[str, Any]]:
        """Fetch a single random testimonial from the collection."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM testimonials ORDER BY RANDOM() LIMIT 1"
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_calendar_config(self) -> Dict[str, Dict[str, Any]]:
        """Fetch the full calendar weights configuration mapped by pillar name."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM calendar_config") as cursor:
                rows = await cursor.fetchall()
                return {row["pillar"]: dict(row) for row in rows}

    async def mark_topic_used(self, topic_id: str, last_used_date: str):
        """Mark a topic as used and increment its usage metrics."""
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """UPDATE topics_bank 
                   SET used = 1, last_used = ?, times_used = times_used + 1 
                   WHERE topic_id = ?""",
                (last_used_date, topic_id)
            )
            await conn.commit()
            logger.info("Topic marked as used", topic_id=topic_id, last_used=last_used_date)
