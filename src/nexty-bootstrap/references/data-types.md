# Data Types Reference

## Primitive types

```python
from nxd.spec.data_types import (
    string, int64, int32, int8, uint64,
    float64, double, number, boolean, date, binary
)
```

| Type | Example |
|------|---------|
| `string()` | Text fields |
| `int64()` | Large integers, IDs |
| `int32()` | Standard integers |
| `int8()` | Small integers |
| `uint64()` | Unsigned large integers |
| `float64()` | Floating point |
| `double()` | Double precision float |
| `number()` | Generic numeric |
| `boolean()` | True/false |
| `date()` | Calendar date |
| `binary()` | Raw bytes |

---

## Complex types

```python
from nxd.spec.data_types import (
    timestamp, decimal, duration, vector_embeddings,
    list as list_type, map as map_type, struct
)
from nxd.spec.data_types import Field
```

### Timestamp

```python
timestamp(unit="ms", timezone="UTC")
timestamp(unit="us", timezone="America/New_York")
```

### Decimal

```python
decimal(precision=38, scale=10)   # financial amounts
decimal(precision=10, scale=2)    # currency
```

### Duration

```python
duration(unit="ms")
```

### Vector embeddings

```python
vector_embeddings(dimensions=1536)   # OpenAI ada-002
vector_embeddings(dimensions=768)    # BERT-base
```

### List

```python
list_type(string())
list_type(int64())
```

### Map

```python
map_type(string(), int64())
map_type(string(), string())
```

### Struct

```python
struct([
    Field("country", string()),
    Field("region", string()),
    Field("score", float64()),
])
```

---

## Usage in semantic_model

```python
from nxd.spec import semantic_model
from nxd.spec.data_types import (
    int64, string, timestamp, decimal, list as list_type, struct, Field
)

order_model = semantic_model("orders").schema({
    "order_id":   string(),
    "amount":     decimal(precision=38, scale=10),
    "created_at": timestamp(unit="ms", timezone="UTC"),
    "tags":       list_type(string()),
    "address":    struct([
        Field("city", string()),
        Field("zip", string()),
    ]),
})
```
