"""IR interpreter, pre-COPY contract, validators (plan §8).

`import_run_id` is allocated before any staging table. The retry policy
is keyed by `import_runs.status` (plan §8.4). All loads go through
`COPY FROM STDIN` via psycopg3.
"""
