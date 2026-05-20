"""DDL generation + identifier sanitization (plan §5, §8.2).

Target tables live in the managed schema (default `structai_user`).
v1 never writes to or drops tables outside it.
"""
