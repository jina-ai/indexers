__copyright__ = "Copyright (c) 2021 Jina AI Limited. All rights reserved."
__license__ = "Apache-2.0"

from typing import Tuple, Generator, Dict, List

import numpy as np
from jina.logging.logger import JinaLogger
from jina import Executor, requests, DocumentArray
from jina_commons.indexers.dump import export_dump_streaming

from .mongohandler import MongoHandler


class MongoDBStorage(Executor):
    def __init__(
        self,
        host: str = 'localhost',
        port: int = 27017,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: str = 'jina_index',
        collection: str = 'jina_index',
        default_traversal_paths: List[str] = ['r'],
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._logger = JinaLogger('mongo_handler')
        self._handler = MongoHandler(
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
            collection=collection,
        )
        self._traversal_paths = default_traversal_paths

    @requests(on='/index')
    def add(self, docs: DocumentArray, parameters: Dict, **kwargs):
        """Add Documents to Postgres

        :param docs: list of Documents
        :param parameters: parameters to the request
        """
        traversal_paths = parameters.get('traversal_paths', self._traversal_paths)
        with self._handler as mongo_handler:
            mongo_handler.add(docs.traverse_flat(traversal_paths))

    @requests(on='/update')
    def update(self, docs: DocumentArray, parameters: Dict, **kwargs):
        """Updated document from the database.

        :param docs: list of Documents
        :param parameters: parameters to the request
        """
        traversal_paths = parameters.get('traversal_paths', self._traversal_paths)
        with self.handler as mongo_handler:
            mongo_handler.update(docs.traverse_flat(traversal_paths))

    @requests(on='/delete')
    def delete(self, docs: DocumentArray, parameters: Dict, **kwargs):
        """Delete document from the database.

        :param docs: list of Documents
        :param parameters: parameters to the request
        """
        traversal_paths = parameters.get('traversal_paths', self._traversal_paths)
        with self.handler as mongo_handler:
            mongo_handler.delete(docs.traverse_flat(traversal_paths))

    @requests(on='/search')
    def search(self, docs: DocumentArray, parameters: Dict, **kwargs):
        """Get the Documents by the ids of the docs in the DocArray

        :param docs: the DocumentArray to search with (they only need to have the `.id` set)
        :param parameters: the parameters to this request
        """
        traversal_paths = parameters.get('traversal_paths', self._traversal_paths)

        with self.handler as mongo_handler:
            mongo_handler.search(docs.traverse_flat(traversal_paths))

    @requests(on='/dump')
    def dump(self, parameters: Dict, **kwargs):
        """Dump the index

        :param parameters: a dictionary containing the parameters for the dump
        """

        path = parameters.get('dump_path')
        if path is None:
            self.logger.error(f'No "dump_path" provided for {self}')

        shards = int(parameters.get('shards'))
        if shards is None:
            self.logger.error(f'No "shards" provided for {self}')

        export_dump_streaming(
            path, shards=shards, size=self.size, data=self._get_generator()
        )

    def _get_generator(self) -> Generator[Tuple[str, np.array, bytes], None, None]:
        with self.handler as mongo_handler:
            # always order the dump by id as integer
            cursor = mongo_handler.collection.find({})
            for document in cursor:
                yield document