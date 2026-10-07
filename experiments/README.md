# Sequential and concurrent search

Run from the project root:

```bash
uv run -m experiments.search_load
```

The script simulates three sources with delays of 50, 100, and 200 ms using
`asyncio.sleep`. It compares sequential awaits in a loop with the actual
`SearchService`, checking identical results and no provider failures.
After one warm-up per mode, it takes five measurements per mode, alternating
execution order, and prints median times and speedup. Logging is disabled;
no external API access or token is required.

Each search runs separately without competing load. The timeout is 5 seconds,
and the limit is 3 requests per provider. The script overwrites
[results/search_load.json](results/search_load.json), which contains all samples,
parameters, the measurement timestamp, and environment details. See the
[main README](../README.md#key-experiment) for results and their explanation.
