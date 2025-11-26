import builtins
import io
from typing import Generator, Optional

import patroni_compare_config
import pytest
from patroni_compare_config import RESTART_KEYS, compare_dicts, flatten_dict


class TestFlattenDict:
    """
    Test cases for the :func:`flatten_dict` function.
    """

    def test_flatten_simple(self) -> None:
        """
        Test flattening a simple dictionary.
        """
        d = {"a": 1, "b": 2}
        assert flatten_dict(d) == {"a": 1, "b": 2}

    def test_flatten_nested(self) -> None:
        """
        Test flattening a nested dictionary.
        """
        d = {"a": {"b": {"c": 3}}, "d": 4}
        assert flatten_dict(d) == {"a.b.c": 3, "d": 4}

    def test_flatten_mixed(self) -> None:
        """
        Test flattening a mixed dictionary.
        """
        d = {"a": {"b": 2}, "c": 3}
        assert flatten_dict(d) == {"a.b": 2, "c": 3}

    def test_flatten_empty(self) -> None:
        """
        Test flattening an empty dictionary.
        """
        assert flatten_dict({}) == {}

    def test_flatten_with_custom_sep(self) -> None:
        """
        Test flattening with a custom separator.
        """
        d = {"a": {"b": 2}}
        assert flatten_dict(d, sep="_") == {"a_b": 2}


class TestCompareDicts:
    """
    Test cases for the :func:`compare_dicts` function.
    """

    def test_compare_added(self) -> None:
        """
        Test comparing dictionaries with added keys.
        """
        old = {"a": 1}
        new = {"a": 1, "b": 2}
        result = compare_dicts(old, new)
        assert result["added"] == {"b": 2}
        assert result["removed"] == {}
        assert result["modified"] == {}

    def test_compare_removed(self) -> None:
        """
        Test comparing dictionaries with removed keys.
        """
        old = {"a": 1, "b": 2}
        new = {"a": 1}
        result = compare_dicts(old, new)
        assert result["added"] == {}
        assert result["removed"] == {"b": 2}
        assert result["modified"] == {}

    def test_compare_modified(self) -> None:
        """
        Test comparing dictionaries with modified keys.
        """
        old = {"a": 1, "b": 2}
        new = {"a": 1, "b": 3}
        result = compare_dicts(old, new)
        assert result["added"] == {}
        assert result["removed"] == {}
        assert result["modified"] == {"b": {"old": 2, "new": 3}}

    def test_compare_all(self) -> None:
        """
        Test comparing dictionaries with all types of changes.
        """
        old = {"a": 1, "b": 2}
        new = {"b": 3, "c": 4}
        result = compare_dicts(old, new)
        assert result["added"] == {"c": 4}
        assert result["removed"] == {"a": 1}
        assert result["modified"] == {"b": {"old": 2, "new": 3}}

    def test_compare_no_change(self) -> None:
        """
        Test comparing dictionaries with no changes.
        """
        old = {"a": 1}
        new = {"a": 1}
        result = compare_dicts(old, new)
        assert result["added"] == {}
        assert result["removed"] == {}
        assert result["modified"] == {}


class TestRestartKeys:
    """
    Test cases for the :const:`RESTART_KEYS` constant.
    """

    def test_restart_keys_are_strings(self) -> None:
        """
        Test that all restart keys are strings.
        """
        for key in RESTART_KEYS:
            assert isinstance(key, str)
        # Check a known restart key
        assert "etcd3.cacert" in RESTART_KEYS


class DummyModule:
    """
    Dummy replacement for :class:`AnsibleModule` to capture :func:`exit_json` and
    :func:`fail_json` calls.
    """

    def __init__(self, params: dict) -> None:
        """
        Initialize the :class:`DummyModule` with the given parameters.
        """
        self.params = params
        self.exit_json_called = False
        self.exit_json_args = None
        self.fail_json_called = False
        self.fail_json_args = None

    def exit_json(self, **kwargs) -> None:
        """
        Simulate the :func:`exit_json` method of :class:`AnsibleModule`.
        """
        self.exit_json_called = True
        self.exit_json_args = kwargs
        raise SystemExit  # To break out of run_module

    def fail_json(self, **kwargs) -> None:
        """
        Simulate the :func:`fail_json` method of :class:`AnsibleModule`.
        """
        self.fail_json_called = True
        self.fail_json_args = kwargs
        raise SystemExit


@pytest.fixture(autouse=True)
def patch_ansible_module(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """
    Patch :class:`AnsibleModule` in :mod:`patroni_compare_config` to use
    :class:`DummyModule`.
    """

    def _ansible_module(**kwargs) -> DummyModule:
        params = {}
        for k, v in kwargs.get("argument_spec", {}).items():
            params[k] = v.get("default", None)
        return DummyModule(params)

    monkeypatch.setattr(patroni_compare_config, "AnsibleModule", lambda **kwargs: None)
    yield


def run_module_with_params(
    monkeypatch: pytest.MonkeyPatch,
    params: dict,
) -> DummyModule:
    """
    Helper to run :func:`run_module` with given *params*.

    :param monkeypatch: The monkeypatch fixture.
    :param params: The parameters to pass to the module.

    :return: the :class:`DummyModule` instance after :func:`run_module`.
    """
    # Patch AnsibleModule to return our DummyModule with params
    dummy = DummyModule(params)
    monkeypatch.setattr(patroni_compare_config, "AnsibleModule", lambda **kwargs: dummy)

    # Run and catch SystemExit
    try:
        patroni_compare_config.run_module()
    except SystemExit:
        pass
    return dummy


class TestRunModule:
    """
    Test cases for the :func:`run_module` function.
    """

    def test_empty_old_config_reports_all_added(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        If old config is empty, all keys are reported as added, action is ``none``.

        :param monkeypatch: The monkeypatch fixture.
        """
        params = {"old_config": {}, "new_config": {"a": 1, "b": {"c": 2}}}
        dummy = run_module_with_params(monkeypatch, params)
        assert dummy.exit_json_called
        result = dummy.exit_json_args
        assert result["changed"] is True
        assert result["action"] == "none"
        assert result["added"] == {"a": 1, "b.c": 2}
        assert result["removed"] == {}
        assert result["modified"] == {}

    def test_no_changes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        If configs are the same, changed is ``False``, action is ``none``.

        :param monkeypatch: The monkeypatch fixture.
        """
        params = {
            "old_config": {"a": 1, "b": {"c": 2}},
            "new_config": {"a": 1, "b": {"c": 2}},
        }
        dummy = run_module_with_params(monkeypatch, params)
        assert dummy.exit_json_called
        result = dummy.exit_json_args
        assert result["changed"] is False
        assert result["action"] == "none"
        assert result["added"] == {}
        assert result["removed"] == {}
        assert result["modified"] == {}

    def test_reload_action(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        If there are changes but not in :data:`RESTART_KEYS`, action is ``reload``.

        :param monkeypatch: The monkeypatch fixture.
        """
        params = {"old_config": {"a": 1}, "new_config": {"a": 2}}
        dummy = run_module_with_params(monkeypatch, params)
        assert dummy.exit_json_called
        result = dummy.exit_json_args
        assert result["changed"] is True
        assert result["action"] == "reload"
        assert result["added"] == {}
        assert result["removed"] == {}
        assert result["modified"] == {"a": {"old": 1, "new": 2}}

    def test_restart_action(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        If a :data:`RESTART_KEY` is changed, action is ``restart``.

        :param monkeypatch: The monkeypatch fixture.
        """
        params = {
            "old_config": {"etcd3": {"cacert": "oldcert"}},
            "new_config": {"etcd3": {"cacert": "newcert"}},
        }
        dummy = run_module_with_params(monkeypatch, params)
        assert dummy.exit_json_called
        result = dummy.exit_json_args
        assert result["changed"] is True
        assert result["action"] == "restart"
        assert result["added"] == {}
        assert result["removed"] == {}
        assert result["modified"] == {
            "etcd3.cacert": {"old": "oldcert", "new": "newcert"}
        }
