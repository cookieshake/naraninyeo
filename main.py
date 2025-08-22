import asyncio
import sys

import logfire

if __name__ == "__main__":
    logfire.configure(
        send_to_logfire=False,
        console=logfire.ConsoleOptions(
            verbose=True,
            min_log_level="trace",
            show_project_link=False
        )
    )
    logfire.instrument_httpx()
    logfire.instrument_pydantic_ai()
    logfire.instrument_pymongo()
    # logfire.install_auto_tracing(modules=["naraninyeo"], min_duration=0.01)

    arg = sys.argv[1] if len(sys.argv) > 1 else None
    match arg:
        case "cli":
            from naraninyeo.entrypoints.cli import main
            asyncio.run(main())
        case "kafka":
            from naraninyeo.entrypoints.kafka import main
            asyncio.run(main())
        case _:
            raise ValueError(f"Unknown entrypoint: {arg}. Use 'cli' or 'kafka'.")