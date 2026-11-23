import os
import unittest
from unittest.mock import patch

import shared_service


class SharedModeContractTests(unittest.TestCase):
    def test_local_and_shared_modes_are_explicit_and_independent(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(shared_service.shared_service_enabled())
            self.assertFalse(shared_service.shared_local_storage_enabled())

        with patch.dict(os.environ, {
            "COPY_MAKER_SHARED_MODE": "1",
            "COPY_MAKER_SHARED_LOCAL_STORAGE": "true",
        }, clear=True):
            self.assertTrue(shared_service.shared_service_enabled())
            self.assertTrue(shared_service.shared_local_storage_enabled())

        with patch.dict(os.environ, {"COPY_MAKER_SHARED_MODE": "off"}, clear=True):
            self.assertFalse(shared_service.shared_service_enabled())
            self.assertFalse(shared_service.shared_local_storage_enabled())


if __name__ == "__main__":
    unittest.main()
