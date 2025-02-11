import queue
import sys
import time
from threading import Thread

from modules.battle import BattleHandler, check_lead_can_battle, RotatePokemon
from modules.console import console
from modules.context import context
from modules.memory import get_game_state, GameState
from modules.menuing import MenuWrapper, CheckForPickup, should_check_for_pickup
from modules.pokemon import opponent_changed, get_opponent


# Contains a queue of tasks that should be run the next time a frame completes.
# This is currently used by the HTTP server component (which runs in a separate thread) to trigger things
# such as extracting the current party, which need to be done from the main thread.
# Each entry here will be executed exactly once and then removed from the queue.
work_queue: queue.Queue[callable] = queue.Queue()


def main_loop() -> None:
    """
    This function is run after the user has selected a profile and the emulator has been started.
    """
    from modules.encounter import encounter_pokemon  # prevents instantiating TotalStats class before profile selected

    pickup_checked = False
    lead_rotated = False

    try:
        mode = None

        if context.config.discord.rich_presence:
            from modules.discord import discord_rich_presence

            Thread(target=discord_rich_presence).start()

        if context.config.obs.http_server.enable:
            from modules.web.http import http_server

            Thread(target=http_server).start()

        while True:
            while not work_queue.empty():
                callback = work_queue.get_nowait()
                callback()

            if (
                not mode
                and get_game_state() == GameState.BATTLE
                and context.bot_mode not in ["Starters", "Static Soft Resets"]
            ):
                if opponent_changed():
                    pickup_checked = False
                    lead_rotated = False
                    encounter_pokemon(get_opponent())
                if context.bot_mode != "Manual":
                    mode = BattleHandler()

            if context.bot_mode == "Manual":
                if mode:
                    mode = None

            elif not mode and context.config.battle.pickup and should_check_for_pickup() and not pickup_checked:
                pickup_checked = True
                mode = MenuWrapper(CheckForPickup())

            elif (
                not mode
                and context.config.battle.replace_lead_battler
                and not check_lead_can_battle()
                and not lead_rotated
            ):
                lead_rotated = True
                mode = MenuWrapper(RotatePokemon())

            elif not mode:
                match context.bot_mode:
                    case "Spin":
                        from modules.modes.general import ModeSpin

                        mode = ModeSpin()

                    case "Starters":
                        from modules.modes.starters import ModeStarters

                        mode = ModeStarters()

                    case "Fishing":
                        from modules.modes.general import ModeFishing

                        mode = ModeFishing()

                    case "Bunny Hop":
                        from modules.modes.general import ModeBunnyHop

                        mode = ModeBunnyHop()

                    case "Static Soft Resets":
                        from modules.modes.soft_resets import ModeStaticSoftResets

                        mode = ModeStaticSoftResets()

                    case "Tower Duo":
                        from modules.modes.tower_duo import ModeTowerDuo

                        mode = ModeTowerDuo()

                    case "Ancient Legendaries":
                        from modules.modes.ancient_legendaries import ModeAncientLegendaries

                        mode = ModeAncientLegendaries()
            try:
                if mode:
                    next(mode.step())
            except StopIteration:
                mode = None
                continue
            except:
                mode = None
                context.set_manual_mode()

            context.emulator.run_single_frame()
            if context.config.auto_save.save_state.enable:
                auto_save_state()

    except SystemExit:
        raise
    except:
        console.print_exception(show_locals=True)
        sys.exit(1)


last_saved = -1


def auto_save_state():
    current_ms = int(time.time() * 1000)
    save_backups = context.config.auto_save.save_state.save_as_backups
    global last_saved
    if last_saved == -1:
        last_saved = current_ms
        context.emulator.create_save_state(make_backup=save_backups)
        return
    ms = context.config.auto_save.save_state.seconds_interval * 1000

    if current_ms - last_saved > ms:
        context.emulator.create_save_state(make_backup=save_backups)
        last_saved = current_ms

