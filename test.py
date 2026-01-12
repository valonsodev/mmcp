import asyncio

from src.marketplace import search


async def main() -> None:
    result = await search("google pixel")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
