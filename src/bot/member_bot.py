"""서버 입장 멤버에게 "관객" 역할을 자동 부여하는 Discord 게이트웨이 봇.

폴러와 같은 GitHub Actions 잡에서 나란히 실행된다. 잡 교체 공백 중 입장한
멤버는 다음 잡 시작 시 전체 멤버 스캔(reconcile)으로 소급 부여된다.

필요 조건:
- Developer Portal에서 SERVER MEMBERS INTENT 활성화
- 봇에 "역할 관리하기" 권한 + 봇 역할이 "관객" 역할보다 위에 있어야 함
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import discord

logger = logging.getLogger(__name__)


class MemberRoleBot(discord.Client):
    def __init__(self, role_name: str, max_runtime_sec: float = 0.0):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(intents=intents)
        self._role_name = role_name
        self._max_runtime_sec = max_runtime_sec

    async def setup_hook(self) -> None:
        if self._max_runtime_sec:
            asyncio.create_task(self._close_after_max_runtime())

    async def _close_after_max_runtime(self) -> None:
        await asyncio.sleep(self._max_runtime_sec)
        logger.info("최대 실행 시간 도달, 정상 종료")
        await self.close()

    async def on_ready(self) -> None:
        logger.info("로그인: %s, 서버 %d곳", self.user, len(self.guilds))
        for guild in self.guilds:
            await self._reconcile(guild)

    async def on_member_join(self, member: discord.Member) -> None:
        role = self._find_role(member.guild)
        if role is not None and not member.bot:
            await self._grant(member, role)

    async def _reconcile(self, guild: discord.Guild) -> None:
        """역할이 없는 기존 멤버 전원에게 소급 부여한다."""
        role = self._find_role(guild)
        if role is None:
            return
        granted = 0
        async for member in guild.fetch_members(limit=None):
            if not member.bot and role not in member.roles:
                if await self._grant(member, role):
                    granted += 1
        if granted:
            logger.info("[%s] 소급 부여 %d명", guild.name, granted)

    def _find_role(self, guild: discord.Guild):
        role = discord.utils.get(guild.roles, name=self._role_name)
        if role is None:
            logger.warning('[%s] "%s" 역할이 없습니다 — 서버 설정에서 만들어주세요', guild.name, self._role_name)
        return role

    async def _grant(self, member: discord.Member, role: discord.Role) -> bool:
        try:
            await member.add_roles(role, reason="입장 시 관객 역할 자동 부여")
            logger.info("[%s] %s ← %s 부여", member.guild.name, member.display_name, role.name)
            return True
        except discord.Forbidden:
            logger.error(
                '권한 부족: 봇 역할이 "%s"보다 위에 있는지, 역할 관리 권한이 있는지 확인하세요', role.name
            )
        except discord.HTTPException as e:
            logger.error("역할 부여 실패(%s): %s", member.display_name, e)
        return False


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if not token:
        # 토큰 미설정 환경(Secret 등록 전)에서도 폴러 잡이 실패하지 않도록 조용히 종료
        logger.info("DISCORD_BOT_TOKEN이 없어 멤버 봇을 건너뜁니다")
        return 0
    role_name = os.environ.get("AUDIENCE_ROLE_NAME", "관객")
    max_runtime = float(os.environ.get("MAX_RUNTIME_SEC", "0"))
    bot = MemberRoleBot(role_name, max_runtime)
    bot.run(token, log_handler=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
