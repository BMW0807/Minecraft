import minecraft_launcher_lib
import os
import subprocess

minecraft_directory = os.path.join(os.getcwd(), ".minecraft")


version_id = "1.21.11"

print("Pobieranie Minecraft")

minecraft_launcher_lib.install.install_minecraft_version(
    version_id, minecraft_directory
)

#Konfiguracja
options = {
    "username": "Testuser",
    "uuid": "",
    "token": "",
}


#Start Mc
minecraft_command = minecraft_launcher_lib.command.get_minecraft_command(
    version_id, minecraft_directory, options
)

print("Uruchamianie Minecrafta...")
subprocess.call(minecraft_command)