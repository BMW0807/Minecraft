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

        typ_instalacji = input(
            "Wybierz instalację [v]anilla/[f]abric (domyślnie vanilla): "
        ).strip().lower()
        if typ_instalacji not in ("", "v", "f"):
            raise ValueError("Nieprawidłowy typ instalacji. Wybierz v albo f.")

        version_to_launch = self.version_id
        if typ_instalacji == "f":
            fabric = minecraft_launcher_lib.mod_loader.get_mod_loader("fabric")
            version_to_launch = fabric.install(
                self.version_id, self.minecraft_directory
            )
            print(f"Zainstalowano Fabric dla Minecrafta {self.version_id}.")

        self.nazwa = input("Podaj nazwę użytkownika: ")

        # Konfiguracja
        options = {
            "username": self.nazwa,
            "uuid": "",
            "token": "",
        }

        # Start Mc
        minecraft_command = minecraft_launcher_lib.command.get_minecraft_command(
            version_to_launch, self.minecraft_directory, options
        )

        subprocess.call(minecraft_command)
