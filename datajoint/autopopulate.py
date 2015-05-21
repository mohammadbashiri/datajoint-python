from .relational_operand import RelationalOperand
from . import DataJointError, TransactionError, Relation
import abc
import logging

# noinspection PyExceptionInherit,PyCallingNonCallable

logger = logging.getLogger(__name__)


class AutoPopulate(metaclass=abc.ABCMeta):
    """
    AutoPopulate is a mixin class that adds the method populate() to a Relation class.
    Auto-populated relations must inherit from both Relation and AutoPopulate,
    must define the property pop_rel, and must define the callback method make_tuples.
    """

    @abc.abstractproperty
    def populate_relation(self):
        """
        Derived classes must implement the read-only property populate_relation, which is the
        relational expression that defines how keys are generated for the populate call.
        By default, populate relation is the join of the primary dependencies of the table.
        """
        pass

    @abc.abstractmethod
    def _make_tuples(self, key):
        """
        Derived classes must implement method _make_tuples that fetches data from tables that are
        above them in the dependency hierarchy, restricting by the given key, computes dependent
        attributes, and inserts the new tuples into self.
        """
        pass

    @property
    def target(self):
        return self

    def populate(self, restriction=None, suppress_errors=False, reserve_jobs=False):
        """
        rel.populate() calls rel._make_tuples(key) for every primary key in self.pop_rel
        for which there is not already a tuple in rel.
        """
        assert not reserve_jobs, NotImplemented   # issue #5
        error_list = [] if suppress_errors else None
        if not isinstance(self.populate_relation, RelationalOperand):
            raise DataJointError('Invalid populate_relation value')
        self.conn._cancel_transaction()  # rollback previous transaction, if any
        unpopulated = (self.populate_relation - self.target) & restriction
        for key in unpopulated.project():
            self.conn._start_transaction()
            if key in self.target:  # already populated
                self.conn._cancel_transaction()
            else:
                logger.info('Populating: ' + str(key))
                try:
                    self._make_tuples(key)
                except Exception as error:
                    self.conn._cancel_transaction()
                    if not suppress_errors:
                        raise
                    else:
                        print(error)
                        error_list.append((key, error))
                else:
                    self.conn._commit_transaction()
        logger.info('Done populating.')
        return error_list


    def populate(self, restriction=None, suppress_errors=False, reserve_jobs=False):
        """
        rel.populate() calls rel._make_tuples(key) for every primary key in self.populate_relation
        for which there is not already a tuple in rel.

        :param restriction: restriction on rel.populate_relation - target
        :param suppress_errors: suppresses error if true
        :param reserve_jobs: currently not implemented
        """
        assert not reserve_jobs, NotImplemented  # issue #5

        error_list = [] if suppress_errors else None

        if not isinstance(self, Relation):
            raise DataJointError('Autopopulate is a mixin for Relation and must therefore subclass Relation')


        if not isinstance(self.populate_relation, RelationalOperand):
            raise DataJointError('Invalid populate_relation value')

        unpopulated = (self.populate_relation - self.target) & restriction

        max_attempts = 10
        for key in unpopulated.project():
            try:
                for attempts in range(max_attempts):
                    try:
                        with self.conn.transaction():
                            if key not in self.target:  # key not populated yet
                                logger.info('Populating: ' + str(key))
                                self._make_tuples(dict(key))
                        break
                    except TransactionError as tr_err:
                        tr_err.resolve()
                        logger.info('Transaction error in {0:s}.'.format(tr_err.culprit))
                else:
                    raise DataJointError(
                        '%s._make_tuples failed after multiple attempts, giving up' % self.__class__)
            except Exception as error:
                if not suppress_errors:
                    raise
                else:
                    print(error)
                    error_list.append((key, error))
        logger.info('Done populating.')
        return error_list
