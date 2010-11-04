import py

class TestCollector:
    def test_collect_versus_item(self):
        from pytest.collect import Collector, Item
        assert not issubclass(Collector, Item)
        assert not issubclass(Item, Collector)

    def test_compat_attributes(self, testdir, recwarn):
        modcol = testdir.getmodulecol("""
            def test_pass(): pass
            def test_fail(): assert 0
        """)
        recwarn.clear()
        assert modcol.Module == py.test.collect.Module
        recwarn.pop(DeprecationWarning)
        assert modcol.Class == py.test.collect.Class
        recwarn.pop(DeprecationWarning)
        assert modcol.Item == py.test.collect.Item
        recwarn.pop(DeprecationWarning)
        assert modcol.File == py.test.collect.File
        recwarn.pop(DeprecationWarning)
        assert modcol.Function == py.test.collect.Function
        recwarn.pop(DeprecationWarning)

    def test_check_equality(self, testdir):
        modcol = testdir.getmodulecol("""
            def test_pass(): pass
            def test_fail(): assert 0
        """)
        fn1 = testdir.collect_by_name(modcol, "test_pass")
        assert isinstance(fn1, py.test.collect.Function)
        fn2 = testdir.collect_by_name(modcol, "test_pass")
        assert isinstance(fn2, py.test.collect.Function)

        assert fn1 == fn2
        assert fn1 != modcol
        if py.std.sys.version_info < (3, 0):
            assert cmp(fn1, fn2) == 0
        assert hash(fn1) == hash(fn2)

        fn3 = testdir.collect_by_name(modcol, "test_fail")
        assert isinstance(fn3, py.test.collect.Function)
        assert not (fn1 == fn3)
        assert fn1 != fn3

        for fn in fn1,fn2,fn3:
            assert fn != 3
            assert fn != modcol
            assert fn != [1,2,3]
            assert [1,2,3] != fn
            assert modcol != fn

    def test_getparent(self, testdir):
        modcol = testdir.getmodulecol("""
            class TestClass:
                 def test_foo():
                     pass
        """)
        cls = testdir.collect_by_name(modcol, "TestClass")
        fn = testdir.collect_by_name(
            testdir.collect_by_name(cls, "()"), "test_foo")

        parent = fn.getparent(py.test.collect.Module)
        assert parent is modcol

        parent = fn.getparent(py.test.collect.Function)
        assert parent is fn

        parent = fn.getparent(py.test.collect.Class)
        assert parent is cls


    def test_getcustomfile_roundtrip(self, testdir):
        hello = testdir.makefile(".xxx", hello="world")
        testdir.makepyfile(conftest="""
            import py
            class CustomFile(py.test.collect.File):
                pass
            def pytest_collect_file(path, parent):
                if path.ext == ".xxx":
                    return CustomFile(path, parent=parent)
        """)
        config = testdir.parseconfig(hello)
        node = testdir.getnode(config, hello)
        assert isinstance(node, py.test.collect.File)
        assert node.name == "hello.xxx"
        id = node.collection.getid(node)
        nodes = node.collection.getbyid(id)
        assert len(nodes) == 1
        assert isinstance(nodes[0], py.test.collect.File)

class TestCollectFS:
    def test_ignored_certain_directories(self, testdir):
        tmpdir = testdir.tmpdir
        tmpdir.ensure("_darcs", 'test_notfound.py')
        tmpdir.ensure("CVS", 'test_notfound.py')
        tmpdir.ensure("{arch}", 'test_notfound.py')
        tmpdir.ensure(".whatever", 'test_notfound.py')
        tmpdir.ensure(".bzr", 'test_notfound.py')
        tmpdir.ensure("normal", 'test_found.py')

        result = testdir.runpytest("--collectonly")
        s = result.stdout.str()
        assert "test_notfound" not in s
        assert "test_found" in s

    def test_custom_norecursedirs(self, testdir):
        testdir.makeini("""
            [pytest]
            norecursedirs = mydir xyz*
        """)
        tmpdir = testdir.tmpdir
        tmpdir.ensure("mydir", "test_hello.py").write("def test_1(): pass")
        tmpdir.ensure("xyz123", "test_2.py").write("def test_2(): 0/0")
        tmpdir.ensure("xy", "test_ok.py").write("def test_3(): pass")
        rec = testdir.inline_run()
        rec.assertoutcome(passed=1)
        rec = testdir.inline_run("xyz123/test_2.py")
        rec.assertoutcome(failed=1)

    def test_found_certain_testfiles(self, testdir):
        p1 = testdir.makepyfile(test_found = "pass", found_test="pass")
        col = testdir.getnode(testdir.parseconfig(p1), p1.dirpath())
        items = col.collect() # Directory collect returns files sorted by name
        assert len(items) == 2
        assert items[1].name == 'test_found.py'
        assert items[0].name == 'found_test.py'

    def test_directory_file_sorting(self, testdir):
        p1 = testdir.makepyfile(test_one="hello")
        p1.dirpath().mkdir("x")
        p1.dirpath().mkdir("dir1")
        testdir.makepyfile(test_two="hello")
        p1.dirpath().mkdir("dir2")
        config = testdir.parseconfig()
        col = testdir.getnode(config, p1.dirpath())
        names = [x.name for x in col.collect()]
        assert names == ["dir1", "dir2", "test_one.py", "test_two.py", "x"]

class TestCollectPluginHookRelay:
    def test_pytest_collect_file(self, testdir):
        tmpdir = testdir.tmpdir
        wascalled = []
        class Plugin:
            def pytest_collect_file(self, path, parent):
                wascalled.append(path)
        config = testdir.Config()
        config.pluginmanager.register(Plugin())
        config.parse([tmpdir])
        col = testdir.getnode(config, tmpdir)
        testdir.makefile(".abc", "xyz")
        res = col.collect()
        assert len(wascalled) == 1
        assert wascalled[0].ext == '.abc'

    def test_pytest_collect_directory(self, testdir):
        tmpdir = testdir.tmpdir
        wascalled = []
        class Plugin:
            def pytest_collect_directory(self, path, parent):
                wascalled.append(path.basename)
                return py.test.collect.Directory(path, parent)
        testdir.plugins.append(Plugin())
        testdir.mkdir("hello")
        testdir.mkdir("world")
        reprec = testdir.inline_run()
        assert "hello" in wascalled
        assert "world" in wascalled
        # make sure the directories do not get double-appended
        colreports = reprec.getreports("pytest_collectreport")
        names = [rep.nodenames[-1] for rep in colreports]
        assert names.count("hello") == 1

class TestPrunetraceback:
    def test_collection_error(self, testdir):
        p = testdir.makepyfile("""
            import not_exists
        """)
        result = testdir.runpytest(p)
        assert "__import__" not in result.stdout.str(), "too long traceback"
        result.stdout.fnmatch_lines([
            "*ERROR collecting*",
            "*mport*not_exists*"
        ])

    def test_custom_repr_failure(self, testdir):
        p = testdir.makepyfile("""
            import not_exists
        """)
        testdir.makeconftest("""
            import py
            def pytest_collect_file(path, parent):
                return MyFile(path, parent)
            class MyError(Exception):
                pass
            class MyFile(py.test.collect.File):
                def collect(self):
                    raise MyError()
                def repr_failure(self, excinfo):
                    if excinfo.errisinstance(MyError):
                        return "hello world"
                    return py.test.collect.File.repr_failure(self, excinfo)
        """)

        result = testdir.runpytest(p)
        result.stdout.fnmatch_lines([
            "*ERROR collecting*",
            "*hello world*",
        ])

    @py.test.mark.xfail(reason="other mechanism for adding to reporting needed")
    def test_collect_report_postprocessing(self, testdir):
        p = testdir.makepyfile("""
            import not_exists
        """)
        testdir.makeconftest("""
            import py
            def pytest_make_collect_report(__multicall__):
                rep = __multicall__.execute()
                rep.headerlines += ["header1"]
                return rep
        """)
        result = testdir.runpytest(p)
        result.stdout.fnmatch_lines([
            "*ERROR collecting*",
            "*header1*",
        ])


class TestCustomConftests:
    def test_ignore_collect_path(self, testdir):
        testdir.makeconftest("""
            def pytest_ignore_collect(path, config):
                return path.basename.startswith("x") or \
                       path.basename == "test_one.py"
        """)
        testdir.mkdir("xy123").ensure("test_hello.py").write(
            "syntax error"
        )
        testdir.makepyfile("def test_hello(): pass")
        testdir.makepyfile(test_one="syntax error")
        result = testdir.runpytest()
        assert result.ret == 0
        result.stdout.fnmatch_lines(["*1 passed*"])

    def test_collectignore_exclude_on_option(self, testdir):
        testdir.makeconftest("""
            collect_ignore = ['hello', 'test_world.py']
            def pytest_addoption(parser):
                parser.addoption("--XX", action="store_true", default=False)
            def pytest_configure(config):
                if config.getvalue("XX"):
                    collect_ignore[:] = []
        """)
        testdir.mkdir("hello")
        testdir.makepyfile(test_world="#")
        reprec = testdir.inline_run(testdir.tmpdir)
        names = [rep.nodenames[-1]
                    for rep in reprec.getreports("pytest_collectreport")]
        assert 'hello' not in names
        assert 'test_world.py' not in names
        reprec = testdir.inline_run(testdir.tmpdir, "--XX")
        names = [rep.nodenames[-1]
                    for rep in reprec.getreports("pytest_collectreport")]
        assert 'hello' in names
        assert 'test_world.py' in names

    def test_pytest_fs_collect_hooks_are_seen(self, testdir):
        conf = testdir.makeconftest("""
            import py
            class MyDirectory(py.test.collect.Directory):
                pass
            class MyModule(py.test.collect.Module):
                pass
            def pytest_collect_directory(path, parent):
                return MyDirectory(path, parent)
            def pytest_collect_file(path, parent):
                return MyModule(path, parent)
        """)
        sub = testdir.mkdir("sub")
        p = testdir.makepyfile("def test_x(): pass")
        result = testdir.runpytest("--collectonly")
        result.stdout.fnmatch_lines([
            "*MyDirectory*",
            "*MyModule*",
            "*test_x*"
        ])
