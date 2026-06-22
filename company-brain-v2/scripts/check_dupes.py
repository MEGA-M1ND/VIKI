import asyncio, ssl, asyncpg

DSN = "postgresql://postgres.skrauwogwxzzzavdnigs:AihDatabase2024@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres"

async def main():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    conn = await asyncpg.connect(DSN, ssl=ctx)

    total = await conn.fetchval("SELECT count(*) FROM memory_records")
    dupes = await conn.fetch("""
        SELECT content, count(*) as n
        FROM memory_records
        GROUP BY content
        HAVING count(*) > 1
        ORDER BY n DESC
        LIMIT 10
    """)
    print(f"Total records: {total}")
    if dupes:
        print(f"Duplicate facts ({len(dupes)} groups):")
        for r in dupes:
            print(f"  x{r['n']} — {r['content'][:100]}")
    else:
        print("No duplicates.")
    await conn.close()

asyncio.run(main())
