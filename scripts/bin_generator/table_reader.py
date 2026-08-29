import tomllib
from typing import TypeAlias

class ConfigError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("\n".join(errors))

def load_toml_file(path: str) -> dict:
    try: 
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError: 
        raise ConfigError([f"{path}: file not found"])
    except IsADirectoryError:
        raise ConfigError([f"{path}: expected TOML file, found directory"])
    except PermissionError:
        raise ConfigError([f"{path}: permission denied"])
    except tomllib.TOMLDecodeError as e:
        raise ConfigError([f"{path}: TOML parse error: {e}"])

TomlTable: TypeAlias = dict[str, object]

_MISSING = object()

class TableReader:
    def __init__(
            self,
            raw: object,
            path: str,
            errors: list[str],
            ) -> None:
        self.path = path
        self.errors = errors
        self.consumed: set[str] = set()

        if isinstance(raw, dict):
            self.values: TomlTable = raw 
        else:
            self.values = {}
            self.errors.append(f"{path}: expected table")

    def _required_value(self, key: str) -> object:
        self.consumed.add(key)

        if key not in self.values:
            self.errors.append(f"{self.path}.{key}: required field")
            return _MISSING 
        return self.values[key]

    def _decode_strings(
            self,
            key: str,
            value: object,
            *,
            min_items: int,
            ) -> tuple[str, ...]:
        if not isinstance(value, list):
            self.errors.append(
                    f"{self.path}.{key}: expected list of strings")
            return ()
        if len(value) < min_items:
            self.errors.append(
                    f"{self.path}.{key}: expected at least {min_items} item(s)")
            return ()

        result: list[str] = []
        for index, item in enumerate(value):
            if not isinstance(item, str) or not item.strip():
                self.errors.append(
                        f"{self.path}.{key}[{index}]: expected non-empty string")
                continue
            result.append(item)
        return tuple(result)

    def required_str(self, key: str) -> str:
        value = self._required_value(key)

        if value is _MISSING:
            return ""

        if not isinstance(value, str) or not value.strip():
            self.errors.append(
                    f"{self.path}.{key}: expected non-empty string")
            return ""
        return value

    def optional_str(
            self,
            key: str,
            *,
            default: str | None = None,
            ) -> str | None:
        self.consumed.add(key)

        if key not in self.values:
            return default 

        value = self.values[key]

        if not isinstance(value, str) or not value.strip():
            self.errors.append(
                    f"{self.path}.{key}: expected non-empty string")
            return default 
        return value 

    def required_int(self, key: str) -> int:
        value = self._required_value(key)

        if value is _MISSING:
            return 0

        if type(value) is not int:
            self.errors.append(
                    f"{self.path}.{key}: expected integer")
            return 0
        return value 

    def required_strings(
            self, 
            key: str,
            *,
            min_items: int = 1,
            ) -> tuple[str, ...]:
        value = self._required_value(key)
        
        if value is _MISSING:
            return ()

        return self._decode_strings(
                key, 
                value,
                min_items=min_items,
                )

    def optional_string(
            self,
            key: str, 
            *,
            default: tuple[str, ...] = (),
            min_items = 0
            ) -> tuple[str, ...]:
        self.consumed.add(key)
        
        if key not in self.values:
            return default 

        return self._decode_strings(
                key,
                self.values[key],
                min_items=min_items,)


    def required_table(self, key: str) -> TomlTable:
        value = self._required_value(key)

        if value is _MISSING:
            return {}

        if not isinstance(value, dict):
            self.errors.append(
                    f"{self.path}.{key}: expected table")
            return {}
        return value 

    def optional_table(self, key: str) -> TomlTable:
        self.consumed.add(key)

        if key not in self.values:
            return {}

        value = self.values[key]

        if not isinstance(value, dict):
            self.errors.append(
                    f"{self.path}.{key}: expected table")
            return {}
        return value 

    def finish(self) -> None:
        unkown = self.values.keys() - self.consumed
        
        for key in sorted(unkown):
            self.errors.append(
                    f"{self.path}.{key}: unknown field")

