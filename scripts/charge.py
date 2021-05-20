"""
Adds the ability to accelerate by pressing V (sneak).

* ``/charge <player>`` to toggle player ability to charge

Options
^^^^^^^

.. code-block:: toml
    [charge]
    cooldown = 10
    duration = 2
    power = 1.7

.. codeauthor:: Jipok
"""

import time
import asyncio

from piqueserver.commands import command, admin, target_player, get_player
from piqueserver.config import config
from pyspades import world


CHARGE_CONFIG = config.section('charge')
CHARGE_COOLDOWN = CHARGE_CONFIG.option('cooldown', 10)
CHARGE_DURATION = CHARGE_CONFIG.option('duration', 2)
CHARGE_POWER = CHARGE_CONFIG.option('power', 1.7)

@command('charge', admin_only=True)
def give_charge(connection, player):
    player = get_player(connection.protocol, player)
    protocol = connection.protocol
    if player in protocol.charge_list:
        protocol.charge_list.remove(player)
        player.send_chat("You lost the charge ability")
    else:
        protocol.charge_list.append(player)
        player.last_charge_time = 0
        player.send_chat("You got the charge ability. Press V (sneak)")

def apply_script(protocol, connection, config):
    class ChargeConnection(connection):
        sneak = False
        charge_save_on_fall = False
        last_charge_time = 0
        need_notice = False

        def on_spawn(self, pos):
            self.last_charge_time = 0
            return connection.on_spawn(self, pos)

        def on_login(self, name):
            connection.on_login(self, name)
            self.protocol.charge_list.append(self)
            self.last_charge_time = 0
            self.send_chat("You got the charge ability. Press V (sneak)")

        def on_animation_update(self, jump, crouch, sneak, sprint):
            if sneak and not self.sneak and self in self.protocol.charge_list:
                if (time.monotonic() >= self.last_charge_time + CHARGE_COOLDOWN.get()) or self.admin:
                    vel = self.world_object.velocity
                    if vel.length() != 0:
                        k = CHARGE_POWER.get() / vel.length()
                        vel.set(*(vel*k).get())
                        self.last_charge_time = time.monotonic()
                        self.charge_save_on_fall = True
                        self.need_notice = True
                else:
                    cur = time.monotonic() - self.last_charge_time
                    self.send_chat_warning("Not ready. Cooldown: %.0f/%.0f sec" % (cur, CHARGE_COOLDOWN.get()))
            self.sneak = sneak
            return connection.on_animation_update(self, jump, crouch, sneak, sprint)

        def on_fall(self, damage: int) -> bool:
            if self in self.protocol.charge_list:
                if time.monotonic() < self.last_charge_time + CHARGE_DURATION.get()*2:
                    if self.charge_save_on_fall:
                        self.charge_save_on_fall = False
                        return False
            return connection.on_fall(self, damage)

    class ChargeProtocol(protocol):
        charge_list = []
        charge_loop_task = None

        async def charge_loop(self):
            while True:
                for player in self.charge_list:
                    if player.world_object is None:
                        continue
                    if time.monotonic() > player.last_charge_time:
                        if time.monotonic() < player.last_charge_time + CHARGE_DURATION.get():
                            if player.charge_save_on_fall:
                                player.set_location()
                    if player.need_notice:
                        if time.monotonic() >= player.last_charge_time + CHARGE_COOLDOWN.get():
                            player.need_notice = False
                            player.send_chat_notice("Charge is ready")
                await asyncio.sleep(1/180) # 60 * 3

        def on_map_change(self, map_):
            if self.charge_loop_task is None:
                self.charge_loop_task = asyncio.ensure_future(self.charge_loop())
            return protocol.on_map_change(self, map_)

        def on_map_leave(self):
            self.charge_loop_task.cancel()
            self.charge_loop_task = None
            protocol.on_map_leave(self)

    return ChargeProtocol, ChargeConnection
