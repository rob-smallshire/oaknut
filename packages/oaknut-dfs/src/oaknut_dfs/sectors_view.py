"""SectorsView: presents multiple sectors as a single buffer-like object."""

from typing import Union


class SectorsView:
    """
    Presents multiple disk sectors as a single logical buffer.

    Supports reads via __getitem__ and writes via __setitem__. For reads,
    data is materialized from the underlying sector views on demand. For writes,
    changes are written back to the underlying sectors immediately.

    This class does not distinguish between physically contiguous and
    non-contiguous sectors - it uses the same code path for both cases.

    Attributes:
        None (implementation details are private)

    Example:
        # Single sector
        view = SectorsView([memoryview(buffer)[0:256]])
        data = view[:100]  # Read first 100 bytes

        # Multiple sectors
        views = [memoryview(buffer)[0:256], memoryview(buffer)[256:512]]
        view = SectorsView(views)
        view[10:20] = b"new data"  # Writes back to underlying buffers
    """

    def __init__(self, views: list[memoryview]):
        """
        Initialize sectors view.

        Args:
            views: List of memoryviews, one per sector (even if just one sector)
        """
        if not isinstance(views, list):
            raise TypeError("views must be a list of memoryview objects")

        self._views = views
        self._length = sum(len(v) for v in self._views)

    def __len__(self) -> int:
        """Get total length in bytes."""
        return self._length

    def __getitem__(self, key: Union[int, slice]) -> Union[int, bytes]:
        """
        Support indexing and slicing for reading.

        Args:
            key: Integer index or slice

        Returns:
            Single byte (as int) for index, bytes for slice

        Raises:
            IndexError: If index out of range
            TypeError: If key is not int or slice
        """
        if isinstance(key, int):
            # Single byte access
            if key < 0:
                key += self._length
            if not 0 <= key < self._length:
                raise IndexError("index out of range")

            # Find which view contains this byte
            offset = 0
            for view in self._views:
                if key < offset + len(view):
                    return view[key - offset]
                offset += len(view)
            raise IndexError("index out of range")

        elif isinstance(key, slice):
            # Slice access - read data
            start, stop, step = key.indices(self._length)

            if step != 1:
                # Non-unit step requires copying byte by byte
                return bytes(self[i] for i in range(start, stop, step))

            if start >= stop:
                return b""

            # Collect bytes from relevant views
            result = bytearray()
            offset = 0

            for view in self._views:
                view_len = len(view)
                view_end = offset + view_len

                # Skip views entirely before our slice
                if view_end <= start:
                    offset = view_end
                    continue

                # Stop once we're past our slice
                if offset >= stop:
                    break

                # This view overlaps our slice
                local_start = max(0, start - offset)
                local_stop = min(view_len, stop - offset)
                result.extend(view[local_start:local_stop])

                offset = view_end

            return bytes(result)
        else:
            raise TypeError(f"indices must be integers or slices, not {type(key).__name__}")

    def __setitem__(self, key: Union[int, slice], value: Union[int, bytes]) -> None:
        """
        Support indexing and slicing for writing.

        Writes are immediately applied to the underlying sector views.

        Args:
            key: Integer index or slice
            value: Byte value (int 0-255) for index, bytes for slice

        Raises:
            IndexError: If index out of range
            TypeError: If key/value types are invalid
            ValueError: If value size doesn't match slice size
        """
        if isinstance(key, int):
            # Single byte write
            if key < 0:
                key += self._length
            if not 0 <= key < self._length:
                raise IndexError("index out of range")

            if not isinstance(value, int):
                raise TypeError("value must be an integer")
            if not 0 <= value <= 255:
                raise ValueError("value must be 0-255")

            # Find which view contains this byte and write it
            offset = 0
            for view in self._views:
                if key < offset + len(view):
                    view[key - offset] = value
                    return
                offset += len(view)
            raise IndexError("index out of range")

        elif isinstance(key, slice):
            # Slice write
            start, stop, step = key.indices(self._length)

            if step != 1:
                raise NotImplementedError("Extended slices not supported for writing")

            if start >= stop:
                if len(value) != 0:
                    raise ValueError("cannot assign non-empty sequence to empty slice")
                return

            slice_len = stop - start
            if len(value) != slice_len:
                raise ValueError(
                    f"value length {len(value)} does not match slice length {slice_len}"
                )

            # Write bytes to relevant views
            value_offset = 0
            offset = 0

            for view in self._views:
                view_len = len(view)
                view_end = offset + view_len

                # Skip views entirely before our slice
                if view_end <= start:
                    offset = view_end
                    continue

                # Stop once we're past our slice
                if offset >= stop:
                    break

                # This view overlaps our slice
                local_start = max(0, start - offset)
                local_stop = min(view_len, stop - offset)
                local_len = local_stop - local_start

                view[local_start:local_stop] = value[value_offset:value_offset + local_len]
                value_offset += local_len

                offset = view_end
        else:
            raise TypeError(f"indices must be integers or slices, not {type(key).__name__}")

    def tobytes(self) -> bytes:
        """
        Convert to bytes.

        Materializes all sectors into a single bytes object.

        Returns:
            bytes containing all data
        """
        result = bytearray(self._length)
        offset = 0
        for view in self._views:
            view_len = len(view)
            result[offset:offset + view_len] = view
            offset += view_len
        return bytes(result)

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"SectorsView({len(self._views)} sectors, {self._length} bytes)"
