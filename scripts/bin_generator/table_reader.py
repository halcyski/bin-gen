import tomllib
from typing import TypeAlias


TomlTable: TypeAlias = dict[str, object]


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

def decode_string_list(
    raw: object,
    path: str,
    errors: list[str],
    min_items: int = 0,) -> tuple[str, ...]:
    if not isinstance(raw, list):
        errors.append(
                f"{path}: expected list of strings")
        return ()
    if len(raw) < min_items:
        errors.append(
                f"{path}: expected at least {min_items} item(s)")
        return ()

    result: list[str] = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            errors.append(
                    f"{path}[{index}]: expected non-empty string")
            continue
        result.append(item)
    return tuple(result)

def decode_table_list(
    raw: object,
    path: str,
    errors: list[str],
    *,
    min_items: int = 0,) -> tuple[TomlTable, ...]:
       if not isinstance(raw, list):
           errors.append(f"{path}: expected list of tables")
           return ()

       if len(raw) < min_items:
           errors.append(
               f"{path}: expected at least {min_items} item(s)"
           )
           return ()

       result: list[TomlTable] = []

       for index, item in enumerate(raw):
           if not isinstance(item, dict):
               errors.append(
                   f"{path}[{index}]: expected table"
               )
               continue

           result.append(item)

       return tuple(result)
        



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

    def required_table_list(
            self,
            key:str,
            *,
            min_items: int = 1,
            ) -> tuple[TomlTable, ...]:
        value = self._required_value(key)

        if value is _MISSING:
            return ()

        return decode_table_list(
                value, 
                f"{self.path}.{key}",
                self.errors,
                min_items=min_items,)


    def decode_strings(
        self,
        key: str,
        value: object,
        *,
        min_items: int,) -> tuple[str, ...]:
            return decode_string_list(
                    value,
                    f"{self.path}.{key}",
                    self.errors,
                    min_items=min_items)

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

        return self.decode_strings(
                key, 
                value,
                min_items=min_items,
                )

    def optional_strings(
            self,
            key: str, 
            *,
            default: tuple[str, ...] = (),
            min_items = 0
            ) -> tuple[str, ...]:
        self.consumed.add(key)
        
        if key not in self.values:
            return default 

        return self.decode_strings(
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

