from unittest.mock import Mock

from celery.concurrency.gevent import TaskPool, Timer, apply_timeout

gevent_modules = (
    'gevent',
    'gevent.greenlet',
    'gevent.monkey',
    'gevent.pool',
    'gevent.signal',
)


class test_gevent_patch:

    def test_is_patched(self):
        self.patching.modules(*gevent_modules)
        patch_all = self.patching('gevent.monkey.patch_all')
        import gevent
        gevent.version_info = (1, 0, 0)
        from celery import maybe_patch_concurrency
        maybe_patch_concurrency(['x', '-P', 'gevent'])
        patch_all.assert_called()


class test_Timer:

    def setup_method(self):
        self.patching.modules(*gevent_modules)
        self.greenlet = self.patching('gevent.greenlet')
        self.GreenletExit = self.patching('gevent.greenlet.GreenletExit')

    def test_sched(self):
        self.greenlet.Greenlet = object
        x = Timer()
        self.greenlet.Greenlet = Mock()
        x._Greenlet.spawn_later = Mock()
        x._GreenletExit = KeyError
        entry = Mock()
        g = x._enter(1, 0, entry)
        assert x.queue

        x._entry_exit(g)
        g.kill.assert_called_with()
        assert not x._queue

        x._queue.add(g)
        x.clear()
        x._queue.add(g)
        g.kill.side_effect = KeyError()
        x.clear()

        g = x._Greenlet()
        g.cancel()


class test_TaskPool:

    def setup_method(self):
        self.patching.modules(*gevent_modules)
        self.spawn_raw = self.patching('gevent.spawn_raw')
        self.Pool = self.patching('gevent.pool.Pool')

    def test_pool(self):
        x = TaskPool()
        x.on_start()
        x.on_stop()
        x.on_apply(Mock())
        x._pool = None
        x.on_stop()

        x._pool = Mock()
        x._pool._semaphore.counter = 1
        x._pool.size = 1
        x.grow()
        assert x._pool.size == 2
        assert x._pool._semaphore.counter == 2
        x.shrink()
        assert x._pool.size, 1
        assert x._pool._semaphore.counter == 1

        x._pool = [4, 5, 6]
        assert x.num_processes == 3

    def test_terminate_job(self):
        func = Mock()
        pool = TaskPool(10)
        pool.on_start()
        pool.on_apply(func)

        assert len(pool._pool_map.keys()) == 1
        pid = list(pool._pool_map.keys())[0]
        greenlet = pool._pool_map[pid]
        greenlet.link.assert_called_once()

        pool.terminate_job(pid)
        import gevent

        gevent.kill.assert_called_once()

    def test_make_killable_target(self):
        def valid_target():
            return "some result..."

        def terminating_target():
            from greenlet import GreenletExit
            raise GreenletExit

        assert TaskPool._make_killable_target(valid_target)() == "some result..."
        assert TaskPool._make_killable_target(terminating_target)() == (False, None, None)

    def test_cleanup_after_job_finish(self):
        testMap = {'1': None}
        TaskPool._cleanup_after_job_finish(None, testMap, '1')
        assert len(testMap) == 0


class test_apply_timeout:

    def test_apply_timeout(self):
        self.patching.modules(*gevent_modules)

        class Timeout(Exception):
            value = None

            def __init__(self, value):
                self.__class__.value = value

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                pass
        timeout_callback = Mock(name='timeout_callback')
        apply_target = Mock(name='apply_target')
        getpid = Mock(name='getpid')
        apply_timeout(
            Mock(), timeout=10, callback=Mock(name='callback'),
            timeout_callback=timeout_callback, getpid=getpid,
            apply_target=apply_target, Timeout=Timeout,
        )
        assert Timeout.value == 10
        apply_target.assert_called()

        apply_target.side_effect = Timeout(10)
        apply_timeout(
            Mock(), timeout=10, callback=Mock(),
            timeout_callback=timeout_callback, getpid=getpid,
            apply_target=apply_target, Timeout=Timeout,
        )
        timeout_callback.assert_called_with(False, 10)
