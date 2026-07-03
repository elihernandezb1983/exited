from .spam import SpamCog
from .access import AccessCog
from .audit import AuditCog
from .gatherings import GatheringsCog
from .panel import PanelCog
from .tickets import TicketsCog
from .war import WarCog


async def setup(bot):
    await bot.add_cog(SpamCog(bot))
    await bot.add_cog(AccessCog(bot))
    await bot.add_cog(AuditCog(bot))
    await bot.add_cog(GatheringsCog(bot))
    await bot.add_cog(PanelCog(bot))
    await bot.add_cog(TicketsCog(bot))
    await bot.add_cog(WarCog(bot))
