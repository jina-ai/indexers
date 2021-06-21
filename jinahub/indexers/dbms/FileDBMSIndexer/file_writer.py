__copyright__ = "Copyright (c) 2021 Jina AI Limited. All rights reserved."
__license__ = "Apache-2.0"

import mmap
import os
from typing import Iterable, Union, List

import numpy as np

from jina import requests

HEADER_NONE_ENTRY = (-1, -1, -1)


class _WriteHandler:
    """
    Write file handler.

    :param path: Path of the file.
    :param mode: Writing mode. (e.g. 'ab', 'wb')
    """

    def __init__(self, path, mode):
        self.path = path
        self.mode = mode
        self.body = open(self.path, self.mode)
        self.header = open(self.path + '.head', self.mode)

    def __enter__(self):
        if self.body.closed:
            self.body = open(self.path, self.mode)
        if self.header.closed:
            self.header = open(self.path + '.head', self.mode)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.flush()

    def close(self):
        """Close the file."""
        if not self.body.closed:
            self.body.close()
        if not self.header.closed:
            self.header.close()

    def flush(self):
        """Clear the body and header."""
        if not self.body.closed:
            self.body.flush()
        if not self.header.closed:
            self.header.flush()


class _ReadHandler:
    """
    Read file handler.

    :param path: Path of the file.
    :param key_length: Length of key.
    """

    def __init__(self, path, key_length):
        self.path = path
        self.header = {}
        if os.path.exists(self.path + '.head'):
            with open(self.path + '.head', 'rb') as fp:
                tmp = np.frombuffer(
                    fp.read(),
                    dtype=[
                        ('', (np.str_, key_length)),
                        ('', np.int64),
                        ('', np.int64),
                        ('', np.int64),
                    ],
                )
                for r in tmp:
                    signature = (r[1], r[2], r[3])
                    if np.array_equal(signature, HEADER_NONE_ENTRY):
                        del self.header[r[0]]
                    else:
                        self.header[r[0]] = signature

            if os.path.exists(self.path):
                self._body = open(self.path, 'r+b')
                self.body = self._body.fileno()
            else:
                raise FileNotFoundError(
                    f'Path not found {self.path}. Querying will not work'
                )
        else:
            raise FileNotFoundError(
                f'Path not found {self.path + ".head"}. Querying will not work'
            )

    def size(self):
        return len(self.header)

    @property
    def total_bytes(self):
        if self.header.values():
            return max(p + m for p, _, m in self.header.values())
        return 0

    def close(self):
        """Close the file."""
        if hasattr(self, '_body'):
            if not self._body.closed:
                self._body.close()


class _CloseHandler:
    def __init__(self, handler: Union['_WriteHandler', '_ReadHandler']):
        self.handler = handler

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.handler is not None:
            self.handler.close()


class FileWriterMixin:
    """Mixing for providing the binarypb writing and reading methods"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._start = 0
        self._page_size = mmap.ALLOCATIONGRANULARITY

    def get_add_handler(self) -> '_WriteHandler':
        """
        Get write file handler.

        :return: write handler
        """
        # keep _start position as in pickle serialization
        return _WriteHandler(self.index_abspath, 'ab')

    def get_create_handler(self) -> '_WriteHandler':
        """
        Get write file handler.

        :return: write handler.
        """

        self._start = 0  # override _start position
        return _WriteHandler(self.index_abspath, 'wb')

    def get_query_handler(self) -> '_ReadHandler':
        """
        Get read file handler.

        :return: read handler.
        """
        return _ReadHandler(self.index_abspath, self.key_length)

    def _add(
        self, keys: Iterable[str], values: Iterable[bytes], write_handler: _WriteHandler
    ):
        for key, value in zip(keys, values):
            l = len(value)  #: the length
            p = (
                int(self._start / self._page_size) * self._page_size
            )  #: offset of the page
            r = (
                self._start % self._page_size
            )  #: the remainder, i.e. the start position given the offset
            # noinspection PyTypeChecker
            write_handler.header.write(
                np.array(
                    (key, p, r, r + l),
                    dtype=[
                        ('', (np.str_, self.key_length)),
                        ('', np.int64),
                        ('', np.int64),
                        ('', np.int64),
                    ],
                ).tobytes()
            )
            self._start += l
            write_handler.body.write(value)
            self._size += 1

    def delete(self, keys: Iterable[str], *args, **kwargs) -> None:
        """Delete the serialized documents from the index via document ids.

        :param keys: a list of ``id``, i.e. ``doc.id`` in protobuf
        :param args: not used
        :param kwargs: not used
        """
        keys = self._filter_nonexistent_keys(keys, self.query_handler.header.keys())
        del self.query_handler
        self.handler_mutex = False
        if keys:
            self._delete(keys)

    def _delete(self, keys: Iterable[str]) -> None:
        with self.write_handler as write_handler:
            for key in keys:
                write_handler.header.write(
                    np.array(
                        tuple(np.concatenate([[key], HEADER_NONE_ENTRY])),
                        dtype=[
                            ('', (np.str_, self.key_length)),
                            ('', np.int64),
                            ('', np.int64),
                            ('', np.int64),
                        ],
                    ).tobytes()
                )
                self._size -= 1

    def _query(self, keys: Iterable[str]) -> List[bytes]:
        query_results = []
        for key in keys:
            pos_info = self.query_handler.header.get(key, None)
            if pos_info is not None:
                p, r, l = pos_info
                with mmap.mmap(self.query_handler.body, offset=p, length=l) as m:
                    query_results.append(m[r:])
            else:
                query_results.append(None)

        return query_results