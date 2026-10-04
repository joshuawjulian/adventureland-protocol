# albot: the small Adventure Land client library of the Learn course.
#
# One module per job (docs/COURSE.md, "Modules and public names"):
#   alsocket   Socket.IO v4 by hand on a plain WebSocket (standalone)
#   api        the HTTP API: login, servers and characters, the socket URL
#   gdata      the game data G: download once per version, keep it on disk
#   world      our copy of the world: me, monsters, players, chests
#   cooldowns  when each skill (and the potion timer) is ready again
#   budget     the call-cost budget, so that the server does not kick us
#   actions    move, attack, heal, loot, respawn (and the Part 3 actions)
#   pathfind   walls and A* (Part 3)
#   bot        the handshake, and Bot.connect() that does all of the above
#
# Import the modules by name, for example `from albot.bot import Bot`.
