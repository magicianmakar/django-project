
class ApiHelperBase:

    def smart_board_sync(self, user, board):
        """
        Add Products to `board` if the config match
        Args:
            user: Parent user
            board: board to add products to

        Raises:
            NotImplementedError: if not not impmented in subsclass
                                 Only implmented in: N/A
        """
        raise NotImplementedError('Smart Board Sync')
