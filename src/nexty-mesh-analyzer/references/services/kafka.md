# Kafka inspection

- **Driver:** `nxd:kafka:1.0.0` — category Storage, storage kind **other** (streaming)
- **Plugin:** not yet built — implement `scripts/drivers/kafka.py` from this recipe
- **Client:** `confluent-kafka` or `kafka-python`

## Attributes

`bootstrap_servers`, `security_protocol`, `sasl_mechanism`, `sasl_username` (`$ConnectionString` for Azure Event Hubs), `sasl_password`, `cloud_provider`.

## Recipe

- List topics via the admin client.
- For each topic, consume a few messages from the beginning with a short timeout to infer schema from the JSON/Avro payload.
- Use a **throwaway consumer group** and **do not commit offsets** — keep it read-only.

Topics are `topic`-kind assets; treat the message payload as the schema.
