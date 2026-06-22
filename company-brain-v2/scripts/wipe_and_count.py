import asyncio, ssl, asyncpg

DSN = "postgresql://postgres.skrauwogwxzzzavdnigs:AihDatabase2024@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres"

async def main():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    conn = await asyncpg.connect(DSN, ssl=ctx)
    before = await conn.fetchval("SELECT count(*) FROM memory_records")
    await conn.execute("DELETE FROM memory_records")
    after = await conn.fetchval("SELECT count(*) FROM memory_records")
    print(f"Deleted {before} records, {after} remaining")
    await conn.close()

asyncio.run(main())
