#!/usr/bin/env python3
"""
GPIO testing tool for libgpiod.
Tests GPIO line functionality for the lock controller.
"""
import argparse
import time
import sys


def test_gpio(chip_name: str, line_number: int, duration: float = 2.0):
    """
    Test GPIO line by toggling it.

    Args:
        chip_name: GPIO chip name (e.g., 'gpiochip0')
        line_number: GPIO line number (e.g., 17)
        duration: Duration to keep GPIO high (seconds)
    """
    try:
        import gpiod
    except ImportError:
        print("ERROR: libgpiod not installed")
        print("Install with: sudo apt install python3-libgpiod")
        sys.exit(1)

    try:
        # Open GPIO chip
        print(f"Opening {chip_name}...")
        chip = gpiod.Chip(chip_name)
        print(f"✓ Chip opened: {chip.name()} ({chip.num_lines()} lines)")

        # Get GPIO line
        print(f"\nGetting line {line_number}...")
        line = chip.get_line(line_number)

        # Check if line is available
        if line.is_used():
            consumer = line.consumer()
            print(f"⚠ WARNING: Line {line_number} is already in use by: {consumer}")
            response = input("Continue anyway? (y/n): ")
            if response.lower() != 'y':
                print("Aborted")
                return

        # Request line as output
        print(f"\nRequesting line {line_number} as output...")
        line.request(
            consumer="gpio_test",
            type=gpiod.LINE_REQ_DIR_OUT,
            default_vals=[0]
        )
        print(f"✓ Line requested successfully")

        # Test sequence
        print(f"\n{'='*50}")
        print("Starting GPIO test sequence")
        print(f"{'='*50}")

        for i in range(3):
            print(f"\nCycle {i+1}/3:")

            # Set HIGH
            print(f"  Setting line {line_number} to HIGH (1)...")
            line.set_value(1)
            print(f"  ✓ GPIO HIGH (relay should activate)")
            print(f"  Waiting {duration} seconds...")
            time.sleep(duration)

            # Set LOW
            print(f"  Setting line {line_number} to LOW (0)...")
            line.set_value(0)
            print(f"  ✓ GPIO LOW (relay should deactivate)")

            if i < 2:
                print(f"  Waiting {duration} seconds...")
                time.sleep(duration)

        # Cleanup
        print(f"\n{'='*50}")
        print("Test completed successfully")
        print(f"{'='*50}")
        print("\nCleaning up...")
        line.release()
        print("✓ Line released")
        chip.close()
        print("✓ Chip closed")

        print("\n✅ GPIO test PASSED")

    except FileNotFoundError as e:
        print(f"\n❌ ERROR: GPIO chip not found: {e}")
        print("\nTroubleshooting:")
        print("  1. Check available chips: gpiodetect")
        print("  2. Check device files: ls -l /dev/gpiochip*")
        sys.exit(1)

    except PermissionError:
        print(f"\n❌ ERROR: Permission denied accessing GPIO")
        print("\nTroubleshooting:")
        print("  1. Add user to gpio group:")
        print(f"     sudo usermod -a -G gpio $USER")
        print("  2. Reboot or re-login")
        print("  3. Check permissions: ls -l /dev/gpiochip*")
        print("  4. Or run with sudo (not recommended): sudo python3 test_gpio.py")
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def list_chips():
    """List available GPIO chips."""
    try:
        import gpiod
    except ImportError:
        print("ERROR: libgpiod not installed")
        print("Install with: sudo apt install python3-libgpiod")
        sys.exit(1)

    import os

    print("Available GPIO chips:")
    print(f"{'='*50}")

    chip_files = [f for f in os.listdir('/dev') if f.startswith('gpiochip')]

    if not chip_files:
        print("No GPIO chips found in /dev")
        return

    for chip_file in sorted(chip_files):
        chip_path = f'/dev/{chip_file}'
        try:
            chip = gpiod.Chip(chip_file)
            print(f"\n{chip_file}:")
            print(f"  Name: {chip.name()}")
            print(f"  Label: {chip.label()}")
            print(f"  Lines: {chip.num_lines()}")
            chip.close()
        except Exception as e:
            print(f"\n{chip_file}: ERROR - {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='GPIO testing tool for libgpiod',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available GPIO chips
  python3 test_gpio.py --list

  # Test GPIO 17 on gpiochip0
  python3 test_gpio.py --chip gpiochip0 --line 17

  # Test with custom duration
  python3 test_gpio.py --chip gpiochip0 --line 17 --duration 5

  # Test GPIO 18
  python3 test_gpio.py --line 18

Note: You may need to add your user to the gpio group:
  sudo usermod -a -G gpio $USER
  sudo reboot
        """
    )

    parser.add_argument(
        '--chip',
        type=str,
        default='gpiochip0',
        help='GPIO chip name (default: gpiochip0)'
    )

    parser.add_argument(
        '--line',
        type=int,
        help='GPIO line number (e.g., 17)'
    )

    parser.add_argument(
        '--duration',
        type=float,
        default=2.0,
        help='Duration to keep GPIO high in seconds (default: 2.0)'
    )

    parser.add_argument(
        '--list',
        action='store_true',
        help='List available GPIO chips and exit'
    )

    args = parser.parse_args()

    if args.list:
        list_chips()
        return

    if args.line is None:
        parser.error("--line is required (unless using --list)")

    print(f"GPIO Test Tool (libgpiod)")
    print(f"{'='*50}")
    print(f"Chip: {args.chip}")
    print(f"Line: {args.line}")
    print(f"Duration: {args.duration}s")
    print(f"{'='*50}\n")

    test_gpio(args.chip, args.line, args.duration)


if __name__ == '__main__':
    main()
