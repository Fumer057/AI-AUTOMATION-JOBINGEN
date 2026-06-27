import asyncio
import sys
import os
from pathlib import Path
from src.utils.config_loader import load_config
from src.data.knowledge_store import KnowledgeStore

async def main():
    print("Loading config...")
    config = load_config("config.yaml")
    
    # Overwrite the db path for testing so we don't interfere with real operational DB
    config.storage.knowledge_database_path = "data/test_knowledge.db"
    
    # Clean up test DB if it exists
    test_db = Path(config.storage.knowledge_database_path)
    if test_db.exists():
        os.remove(test_db)
        print("Removed existing test database.")

    print("Initializing Knowledge Store...")
    ks = KnowledgeStore(config)
    await ks.initialize()
    
    # 1. Verify Calendar config config loading
    print("\n--- Test Case 1: Fetch Calendar Config ---")
    cal = await ks.get_calendar_config()
    print(f"Loaded calendar config weights: {list(cal.keys())}")
    assert "Educate" in cal
    assert cal["Educate"]["target_weight"] == 0.40
    
    # 2. Verify Topics seeding & getters
    print("\n--- Test Case 2: Fetch Available Topics ---")
    edu_topics = await ks.get_available_topics("Educate")
    print(f"Found {len(edu_topics)} Educate topics.")
    assert len(edu_topics) > 0
    assert edu_topics[0]["topic_id"] == "edu_001"
    
    # 3. Verify Testimonials random fetching
    print("\n--- Test Case 3: Get Random Testimonial ---")
    testi = await ks.get_random_testimonial()
    print(f"Testimonial loaded: {testi['name']} - '{testi['quote'][:30]}...'")
    assert testi is not None
    assert testi["name"] in ["Aryan Sharma", "Priya Nair"]
    
    # 4. Verify Featured Jobs sheet fetching
    print("\n--- Test Case 4: Get Featured Jobs ---")
    jobs = await ks.get_featured_jobs()
    print(f"Featured jobs found: {len(jobs)}")
    for j in jobs:
        print(f"  {j['company']} - {j['role']} (Featured: {j['featured']})")
        assert j["featured"] == 1
    assert len(jobs) == 2 # Amazon and Google are featured
    
    # 5. Verify marking topic as used
    print("\n--- Test Case 5: Mark Topic Used ---")
    topic_id = "edu_001"
    await ks.mark_topic_used(topic_id, "2026-06-27")
    
    # Reload topic to verify
    topic = await ks.get_topic_by_id(topic_id)
    assert topic["used"] == 1
    assert topic["last_used"] == "2026-06-27"
    assert topic["times_used"] == 1
    
    # Ensure it's no longer in available topics
    edu_topics_after = await ks.get_available_topics("Educate")
    assert len(edu_topics_after) == len(edu_topics) - 1
    print("Topic marked as used correctly!")
    
    # Clean up test DB after test
    if test_db.exists():
        os.remove(test_db)
        print("Cleaned up test database.")
        
    print("\nSUCCESS: Knowledge Store verified successfully!")

if __name__ == "__main__":
    asyncio.run(main())
