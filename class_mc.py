import minecraft_launcher_lib
import os
import subprocess


class mc:
    def __init__(self):
        self.minecraft_directory = os.path.join(os.getcwd(), ".minecraft")
        self.version_id = input("Podaj wersje minecraft: ")

        print("Pobieranie Minecraft")

        minecraft_launcher_lib.install.install_minecraft_version(
            self.version_id, self.minecraft_directory
        )
        self.nazwa = input("Podaj nazwę użytkownika: ")

        # Konfiguracja
        options = {
            "username": self.nazwa,
            "uuid": "",
            "token": "",
        }

        # Start Mc
        minecraft_command = minecraft_launcher_lib.command.get_minecraft_command(
            self.version_id, self.minecraft_directory, options
        )

        subprocess.call(minecraft_command)
