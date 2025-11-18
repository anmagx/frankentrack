from process_man import ProcessHandler

def main():
    handler = ProcessHandler()
    handler.start_workers()
    try:
        # Main loop: exit and stop workers when the shared stop_event is set
        while not handler.stop_event.wait(timeout=0.5):
            pass  # Event.wait() returns immediately when set
    except KeyboardInterrupt:
        print("[Main] KeyboardInterrupt, shutting down...")
    finally:
        handler.stop_workers()

if __name__ == "__main__":
    main()