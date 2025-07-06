from ...trae_agent.utils.config import Config, load_config
import unittest

class TestUtilsConfigMethods(unittest.TestCase):
    def test_Config_class(self):
        try:
            config = Config()
        except:
            self.fail("handle configuration fail")

if __name__ == "__main__":
    unittest.main()