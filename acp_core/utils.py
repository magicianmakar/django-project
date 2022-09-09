from suredone_core.utils import SureDoneUtils


class AcpUtils(SureDoneUtils):
    def get_product_updates_logs(self, params):
        logs_count = self.get_suredone_product_updates_logs_count(params)
        return logs_count

    def get_product_creation_logs(self, params):
        logs_count = self.get_suredone_product_creation_logs_count(params)
        return logs_count
