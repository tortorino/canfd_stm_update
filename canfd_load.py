import argparse
import can
import struct
import time

class STM32CANFDBootloader:
    def __init__(self, interface='can0'):
        self.bus = can.interface.Bus(channel=interface, bustype='socketcan', fd=True)
        self.TIMEOUT = 1.0
        self.COMMANDS = {
            'get': 0x00,
            'get_version': 0x01,
            'get_id': 0x02,
            'read_memory': 0x11,
            'go': 0x21,
            'write_memory': 0x31,
            'erase_memory': 0x44,
            'write_protect': 0x63,
            'write_unprotect': 0x73,
            'readout_protect': 0x82,
            'readout_unprotect': 0x92
        }

    def send_message(self, data):
        msg = can.Message(arbitration_id=0x111, is_extended_id=False, is_fd=True, bitrate_switch=True, data=data)
        self.bus.send(msg)

        response = self.bus.recv(self.TIMEOUT)
        if response and response.data[0] == 0x79:  # ACK
            return True
        return False

    def get_command(self):
        if not self.send_message(bytes([self.COMMANDS['get']])):
            return None

        num_commands = self.bus.recv(self.TIMEOUT).data[0]
        version = self.bus.recv(self.TIMEOUT).data[0]
        commands = [self.bus.recv(self.TIMEOUT).data[0] for _ in range(num_commands)]

        return version, commands

    def erase_memory(self, start_page, num_pages):
        data = bytes([self.COMMANDS['erase_memory']]) + struct.pack('>HH', start_page, num_pages)
        return self.send_message(data)

    def write_memory(self, address, data):
        addr_bytes = struct.pack('>I', address)
        length = len(data) - 1
        cmd_data = bytes([self.COMMANDS['write_memory']]) + addr_bytes + bytes([length])
        if not self.send_message(cmd_data):
            return False

        chunks = [data[i:i+64] for i in range(0, len(data), 64)]
        for chunk in chunks:
            if not self.send_message(chunk):
                return False

        response = self.bus.recv(self.TIMEOUT)
        return response and response.data[0] == 0x79  # ACK

    def go_command(self, address):
        addr_bytes = struct.pack('>I', address)
        return self.send_message(bytes([self.COMMANDS['go']]) + addr_bytes)

    def upload_firmware(self, file_path, start_address):
        with open(file_path, 'rb') as f:
            firmware_data = f.read()

        # Erase necessary flash pages (simplified, adjust as needed)
        pages_to_erase = (len(firmware_data) + 2047) // 2048  # Assuming 2KB pages
        if not self.erase_memory(0, pages_to_erase):
            print("Failed to erase memory")
            return False

        # Write firmware data
        for i in range(0, len(firmware_data), 256):
            chunk = firmware_data[i:i+256]
            if not self.write_memory(start_address + i, chunk):
                print(f"Failed to write chunk at address 0x{start_address + i:08X}")
                return False

        print("Firmware uploaded successfully")
        return True

def main():
    parser = argparse.ArgumentParser(description="STM32 CAN-FD Bootloader Firmware Uploader")
    parser.add_argument("file", help="Path to the firmware file")
    parser.add_argument("--interface", default="can0", help="CAN interface (default: can0)")
    parser.add_argument("--address", type=lambda x: int(x, 0), default=0x08000000,
                        help="Start address for firmware (default: 0x08000000)")
    args = parser.parse_args()

    bootloader = STM32CANFDBootloader(args.interface)

    version, commands = bootloader.get_command()
    if version is None:
        print("Failed to communicate with bootloader")
        return

    print(f"Bootloader version: {version}")
    print(f"Supported commands: {', '.join([hex(cmd) for cmd in commands])}")

    if bootloader.upload_firmware(args.file, args.address):
        print("Firmware upload completed successfully")
        bootloader.go_command(args.address)
    else:
        print("Firmware upload failed")

if __name__ == "__main__":
    main()