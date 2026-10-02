"""Local-only capability regression corpus; never inspect or print secrets."""

import json
from decimal import Decimal
from types import ModuleType

import numpy as np
import pandas as pd
import pytest
from src.services import gol_sandbox as sandbox
from src.services.gol_capabilities import (
    ALLOWED_BUILTINS,
    ERROR,
    SIZE_ERROR,
    AnalysisRefused,
    AnalysisSizeLimit,
    guarded_getattr,
    guarded_getitem,
    guarded_write,
    library_facades,
    plain_value,
)


@pytest.fixture
def frames():
    teams = pd.DataFrame({"id": [1, 2], "team_id": [101, 102], "name": ["Arsenal", "Chelsea"]})
    tracked = pd.DataFrame(
        {
            "player_api_id": list(range(10, 16)),
            "player_name": ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"],
            "team_id": [1, 1, 2, 2, 1, 2],
            "parent_club": ["Arsenal", "Arsenal", "Chelsea", "Chelsea", "Arsenal", "Chelsea"],
            "status": ["on_loan", "first_team", "academy", "on_loan", "released", "on_loan"],
            "data_source": ["academy"] * 6,
            "updated_at": pd.to_datetime(["2026-09-01"] * 6),
            "position": ["Midfielder"] * 6,
            "nationality": ["Test"] * 6,
            "age": [20] * 6,
            "current_club_name": ["Test FC"] * 6,
        }
    )
    stats = pd.DataFrame(
        {
            "player_api_id": list(range(10, 16)),
            "fixture_id": list(range(6)),
            "team_api_id": [101, 102, 101, 102, 101, 102],
            "season": [2026] * 6,
            "minutes": [900] * 6,
            "goals": [20, 1, 2, 3, 4, 5],
            "assists": [10, 1, 2, 3, 4, 5],
            "rating": [9.0, 6.0, 6.1, 6.2, 6.3, 6.4],
            "decimal_rating": pd.Series(
                [Decimal("9.00"), Decimal("6.00"), None, Decimal("6.20"), Decimal("6.30"), Decimal("6.40")],
                dtype=object,
            ),
            "position": ["M"] * 6,
            "formation": ["4-3-3"] * 6,
            "formation_position": ["CAM"] * 6,
            "competition_name": ["Test League"] * 6,
        }
    )
    for field in (
        "shots_total",
        "shots_on",
        "passes_total",
        "passes_key",
        "tackles_total",
        "tackles_blocks",
        "tackles_interceptions",
        "duels_total",
        "duels_won",
        "dribbles_success",
        "fouls_drawn",
        "fouls_committed",
    ):
        stats[field] = [30, 1, 2, 3, 4, 5]
    stats = pd.concat([stats, stats, stats], ignore_index=True)
    journeys = tracked[["player_api_id", "player_name"]].copy()
    journeys["total_first_team_apps"] = [0, 10, 0, 0, 0, 0]
    entries = stats[["player_api_id", "season", "goals", "assists", "minutes"]].copy()
    entries["appearances"] = 10
    entries["club_name"] = "Test FC"
    entries["level"] = "First Team"
    return {
        "teams": teams,
        "tracked": tracked,
        "fixture_stats": stats,
        "journeys": journeys,
        "journey_entries": entries,
    }


# Trusted test inputs only. The reference exposes the previous raw libraries
# exclusively to legitimate analyses, never to the escape corpus.
LEGITIMATE = [
    ("filter", "result=tracked[tracked['status']=='on_loan'][['player_name','age']]"),
    ("groupby", "result=fixture_stats.groupby('position')['goals'].sum()"),
    (
        "named_agg",
        "result=fixture_stats.groupby('position').agg(goals=('goals','sum'),rating=('rating','mean')).reset_index()",
    ),
    ("dict_agg", "result=fixture_stats.groupby('position').agg({'goals':['sum','mean']})"),
    ("lambda_agg", "result=fixture_stats.groupby('position')['goals'].agg(lambda x:x.max()-x.min())"),
    (
        "merge",
        "result=tracked[['player_api_id','player_name']].merge(fixture_stats[['player_api_id','goals']],on='player_api_id')",
    ),
    (
        "pd_merge",
        "result=pd.merge(tracked[['player_api_id']],fixture_stats[['player_api_id','goals']],on='player_api_id')",
    ),
    ("concat", "result=pd.concat([teams,teams],ignore_index=True)"),
    ("pivot", "result=fixture_stats.pivot_table(index='position',columns='season',values='goals',aggfunc='sum')"),
    ("pd_pivot", "result=pd.pivot_table(fixture_stats,index='position',values='goals',aggfunc='mean')"),
    ("crosstab", "result=pd.crosstab(tracked['status'],tracked['parent_club'])"),
    ("sort", "result=fixture_stats.sort_values('goals',ascending=False).head(3)"),
    ("numeric", "result=pd.to_numeric(pd.Series(['1','2','bad']),errors='coerce')"),
    ("date", "result=pd.to_datetime(pd.Series(['2026-01-02','2026-03-04'])).dt.year"),
    ("date_scalar", "result=pd.Timestamp('2026-01-02')"),
    ("duration", "result=pd.Timedelta(days=2)"),
    ("str", "result=tracked[tracked['player_name'].str.contains('a',case=False)]"),
    ("str_chain", "result=tracked['player_name'].str.lower().str[:2]"),
    ("apply", "result=fixture_stats['goals'].apply(lambda x:x*2)"),
    ("row_apply", "result=fixture_stats.apply(lambda row:row['goals']+row['assists'],axis=1)"),
    ("map", "result=tracked['player_name'].map(lambda x:x.upper())"),
    ("pipe", "result=fixture_stats.pipe(lambda x:x.head(2))"),
    ("transform", "result=fixture_stats.groupby('position')['goals'].transform(lambda x:x-x.mean())"),
    ("comprehension", "result=[x*2 for x in range(5) if x>1]"),
    ("dict_comprehension", "result={str(i):i*i for i in range(3)}"),
    ("zip_unpack", "result=[a+b for a,b in zip([1,2],[3,4])]"),
    ("unpack", "a,b=[1,2]\nresult=a+b"),
    ("loop", "values=[]\nfor x in range(4):\n values.append(x)\nresult=values"),
    ("inplace", "value=1\nvalue+=2\nresult=value"),
    ("write_column", "df=teams.copy()\ndf['score']=[1,2]\nresult=df"),
    ("write_loc", "df=teams.copy()\ndf.loc[0,'name']='Test'\nresult=df"),
    ("write_labels", "df=teams.copy()\ndf.columns=['a','b','c']\nresult=df"),
    ("numpy_math", "result=float(np.sqrt(np.sum(np.array([1,3,5])**2)))"),
    ("numpy_where", "result=np.where(fixture_stats['goals']>4,1,0).tolist()"),
    ("numpy_select", "result=np.select([fixture_stats['goals']>4],[1],default=0).tolist()"),
    ("numpy_array", "a=np.zeros((2,3))\na[0,0]=4\nresult=a.sum().item()"),
    ("numpy_reshape", "result=np.arange(6).reshape(2,3).tolist()"),
    ("numpy_dtype", "result=np.array([1,2],dtype=np.int64).tolist()"),
    ("cut", "result=pd.cut(fixture_stats['goals'],bins=[0,5,25],labels=['low','high']).astype(str)"),
    ("qcut", "result=pd.qcut(fixture_stats['goals'],q=2,labels=False)"),
    ("missing", "result=[pd.isna(pd.NA),pd.notna(1),pd.NaT]"),
    ("nested", "result={'values':[1,{'a':True}]}"),
    ("stat_dispatch", "result=fixture_stats['goals'].agg(['sum','mean'])"),
    ("pd_types", "result=isinstance(teams,pd.DataFrame)"),
]
HELPERS = [
    "academy_comparison()",
    "first_team_graduates('Arsenal')",
    "player_status_breakdown('Chelsea')",
    "active_academy_pipeline()",
    "academy_first_team_apps()",
    "top_loan_performers()",
    "player_career('Alpha')",
    "find_similar_players('Alpha')",
    "find_hidden_talent()",
    "suggest_loan_destinations('Alpha')",
]
LEGITIMATE += [(f"helper_{i}", f"result={call}") for i, call in enumerate(HELPERS)]
LEGITIMATE += [
    ("date_utc", "result=pd.to_datetime(pd.Series(['2026-01-01']),utc=True).dt.strftime('%Y-%m-%d')"),
    ("local_lambda", "offset=2\nresult=fixture_stats['goals'].map(lambda x:x+offset)"),
    ("local_function", "def adjust(x):\n return x+1\nresult=fixture_stats['goals'].apply(adjust)"),
    ("group_iteration", "result=[name for name,group in teams.groupby('id')]"),
    ("dict_items", "result=[k+str(v) for k,v in {'a':1}.items()]"),
    ("kwargs_shape", "result=np.ones(shape=(2,3)).tolist()"),
    ("inferred_shape", "result=np.arange(6).reshape(2,-1).tolist()"),
    ("fstring", "result=[f'{i}: {i:.1f}' for i in range(3)]"),
    ("caught_exception", "try:\n x=1/0\nexcept ZeroDivisionError:\n result=0"),
    ("iterrows", "result=[row['name'] for index,row in teams.iterrows()]"),
    ("itertuples", "result=[row[2] for row in teams.itertuples(index=False,name=None)]"),
    ("to_dict", "result=teams.to_dict(orient='records')"),
    ("raw_apply", "result=fixture_stats[['goals','assists']].apply(lambda row:row.sum(),axis=1,raw=True)"),
]


@pytest.mark.parametrize("name,code", LEGITIMATE, ids=[case[0] for case in LEGITIMATE])
def test_legitimate_matches_raw_library_reference(name, code, frames):
    copies = {name: df.copy(deep=True) for name, df in frames.items()}
    reference = {"pd": pd, "np": np, **copies, **sandbox._build_helpers(copies)}
    exec(code, reference)  # trusted local corpus only
    expected = _legacy_format_result(reference["result"])
    expected["display"] = "table"
    actual = sandbox.execute_analysis(code, frames)
    assert actual == expected
    json.dumps(actual, allow_nan=False)


@pytest.mark.parametrize("module,names,facade_index", [(pd, "PANDAS_NAMES", 0), (np, "NUMPY_NAMES", 1)])
def test_non_allowlisted_library_attributes_are_refused(module, names, facade_index):
    from src.services import gol_capabilities as capabilities

    facade = library_facades()[facade_index]
    allowed = set(getattr(capabilities, names))
    for name in dir(module):
        if not name.startswith("_") and name not in allowed:
            with pytest.raises(AnalysisRefused):
                guarded_getattr(facade, name)
            response = sandbox.execute_analysis(f"result={'pd' if facade_index == 0 else 'np'}.{name}", {})
            assert response["result_type"] == "error"
    for name in allowed:
        assert not isinstance(guarded_getattr(facade, name), ModuleType)


def test_no_introspection_builtins():
    assert not set(ALLOWED_BUILTINS) & {
        "getattr",
        "type",
        "vars",
        "dir",
        "globals",
        "locals",
        "__import__",
        "open",
        "eval",
        "exec",
        "compile",
        "setattr",
        "delattr",
        "__build_class__",
    }


def test_module_guards():
    module = ModuleType("local_dummy")
    with pytest.raises(AnalysisRefused):
        guarded_getattr(module, "anything")
    with pytest.raises(AnalysisRefused):
        guarded_getitem({"module": module}, "module")
    with pytest.raises(AnalysisRefused):
        guarded_getattr(pd.Series([1], name=module), "name")


class Hostile:
    def __str__(self):
        raise AssertionError("coercion hook called")

    def __repr__(self):
        raise AssertionError("representation hook called")

    def __iter__(self):
        raise AssertionError("iterator hook called")


@pytest.mark.parametrize(
    "wrap",
    [
        lambda x: x,
        lambda x: [x],
        lambda x: {"x": x},
        lambda x: pd.DataFrame({"x": [x]}),
        lambda x: pd.DataFrame([[1]], columns=[x]),
        lambda x: pd.Series([1], name=x),
    ],
)
def test_hostile_results_rejected_without_hooks(wrap):
    with pytest.raises(AnalysisRefused):
        sandbox._format_result(wrap(Hostile()))


def test_frame_subclass_is_not_formatted():
    class HostileFrame(pd.DataFrame):
        def head(self, *args, **kwargs):
            raise AssertionError("subclass hook called")

    with pytest.raises(AnalysisRefused):
        sandbox._format_result(HostileFrame({"x": [1]}))


@pytest.mark.parametrize("key", ["pd", "np", "type", "_getattr_", "academy_comparison"])
def test_namespace_cannot_override_capabilities(key):
    assert sandbox.execute_analysis("result=1", {key: pd.DataFrame()})["error"] == ERROR


def test_untrusted_input_object_refused():
    assert sandbox.execute_analysis("result=1", {"df": pd.DataFrame({"x": [Hostile()]})})["error"] == ERROR


def test_write_and_facade_guards():
    for value in (*library_facades(), lambda: 1, ModuleType("dummy")):
        with pytest.raises(AnalysisRefused):
            guarded_write(value)


def test_request_frames_not_mutated(frames):
    original = frames["teams"].copy()
    response = sandbox.execute_analysis("teams.loc[0,'name']='Test'\nresult=teams", frames)
    assert response["result_type"] == "table"
    pd.testing.assert_frame_equal(frames["teams"], original)


def test_loop_bounded_inside_exception_handler(monkeypatch):
    monkeypatch.setattr(sandbox, "MAX_PYTHON_STEPS", 100)
    response = sandbox.execute_analysis("while True:\n try:\n  x=1\n except Exception:\n  pass", {})
    assert response["error"] == "Analysis exceeded its execution limit."


def test_allocation_bound_before_call(monkeypatch):
    calls = []
    monkeypatch.setattr(np, "zeros", lambda *a, **kw: calls.append(True))
    assert sandbox.execute_analysis("result=np.zeros((1000001,))", {})["error"] == SIZE_ERROR
    assert not calls


def test_compilation_bound():
    assert sandbox.execute_analysis("x=1\n" * 6000, {})["error"] == SIZE_ERROR


def test_plain_conversion():
    result = plain_value({"values": [pd.NA, pd.NaT, np.float64(np.nan), np.int64(2), np.bool_(True)]})
    assert result == {"values": [None, None, None, 2, True]}
    json.dumps(result, allow_nan=False)


def test_helper_no_network_fallback(frames, monkeypatch):
    from src.utils import team_resolver

    calls = []
    monkeypatch.setattr(team_resolver, "resolve_team_name", lambda *a, **kw: calls.append(True))
    frames["fixture_stats"]["team_api_id"] = 999999
    response = sandbox.execute_analysis("result=active_academy_pipeline()", frames)
    assert response["result_type"] == "table"
    assert not calls


# Frozen pre-fix formatter, exercised only on the legitimate local corpus.
def _legacy_format_result(result) -> dict:
    """Convert the result variable into a JSON-serializable response."""
    if isinstance(result, pd.DataFrame):
        truncated = len(result) > sandbox.MAX_ROWS
        df = result.head(sandbox.MAX_ROWS)
        # Convert to native Python types for JSON serialization
        rows = []
        for _, row in df.iterrows():
            rows.append([_legacy_safe_value(v) for v in row.values])
        return {
            "result_type": "table",
            "columns": [str(c) for c in df.columns],
            "rows": rows,
            "total_rows": len(result),
            "truncated": truncated,
        }

    if isinstance(result, pd.Series):
        df = result.reset_index()
        df.columns = [str(c) for c in df.columns]
        return _legacy_format_result(df)

    if isinstance(result, (int, float, np.integer, np.floating)):
        return {"result_type": "scalar", "value": _legacy_safe_value(result)}

    if isinstance(result, str):
        return {"result_type": "scalar", "value": result}

    if isinstance(result, (list, tuple)):
        return {"result_type": "list", "items": [_legacy_safe_value(v) for v in result[: sandbox.MAX_ROWS]]}

    if isinstance(result, dict):
        return {"result_type": "dict", "data": {str(k): _legacy_safe_value(v) for k, v in result.items()}}

    return {"result_type": "scalar", "value": str(result)}


def _legacy_safe_value(v):
    """Convert numpy/pandas types to JSON-safe Python natives."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, type(pd.NaT)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return round(float(v), 4)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if isinstance(v, pd.DataFrame):
        return f"[DataFrame: {len(v)} rows × {len(v.columns)} cols]"
    if isinstance(v, pd.Series):
        return v.tolist()
    if isinstance(v, (list, tuple)):
        return [_legacy_safe_value(i) for i in v]
    return v


def test_datetime_cells_are_serializable_and_keep_offset():
    response = sandbox.execute_analysis(
        "result=pd.DataFrame({'date':[pd.Timestamp('2026-07-01',tz='Europe/London')]})", {}
    )
    assert response["rows"] == [["2026-07-01T00:00:00+01:00"]]
    json.dumps(response, allow_nan=False)


def test_nested_input_lists_are_request_local():
    frame = pd.DataFrame({"ids": [[1, 2]]})
    response = sandbox.execute_analysis("df['ids'].iloc[0].append(3)\nresult=df", {"df": frame})
    assert response["rows"] == [[[1, 2, 3]]]
    assert frame.iloc[0, 0] == [1, 2]


@pytest.mark.parametrize(
    "code,error",
    [
        (123, ERROR),
        (["result=1"], ERROR),
        ("result=)", "Analysis refused: syntax error."),
        ('result=df["private-column-label"]', "Analysis refused: KeyError (missing column or label)."),
    ],
)
def test_invalid_code_and_errors_do_not_echo_details(code, error):
    response = sandbox.execute_analysis(code, {"df": pd.DataFrame({"x": [1]})})
    assert response == {"result_type": "error", "error": error, "display": "table"}


def test_large_dtype_is_refused_before_allocation(monkeypatch):
    calls = []
    monkeypatch.setattr(np, "zeros", lambda *a, **kw: calls.append(True))
    response = sandbox.execute_analysis("result=np.zeros(1,dtype='U100000000')", {})
    assert response["error"] == SIZE_ERROR
    assert not calls


def test_output_cap_and_unsafe_tail():
    response = sandbox.execute_analysis("result=pd.DataFrame({'x':list(range(110))})", {})
    assert response["truncated"] and response["total_rows"] == 110
    assert len(response["rows"]) == 100
    refused = sandbox.execute_analysis("result=pd.DataFrame({'x':[1]*101+[sum]})", {})
    assert refused["error"] == ERROR


def test_service_tool_and_completion_use_boundary(frames, monkeypatch):
    from types import SimpleNamespace as NS

    from flask import Flask
    from src.services.gol_service import GolService

    monkeypatch.setenv("API_FOOTBALL_FROZEN", "true")
    for code, ok in [
        ("result=teams[['name']]", True),
        ("result=pd.non_allowlisted_attribute", False),
        ("result=pd.DataFrame", False),
        ("result={'x':sum}", False),
    ]:
        service = GolService.__new__(GolService)
        service.df_cache = NS(get_frames=lambda app: frames)
        service.model = "local-test-model"
        arguments = json.dumps({"code": code, "display": "table"})
        tool = NS(index=0, id="local-tool", function=NS(name="run_analysis", arguments=arguments))
        first = NS(choices=[NS(delta=NS(content=None, tool_calls=[tool]), finish_reason="tool_calls")])
        last = NS(choices=[NS(delta=NS(content=None, tool_calls=None), finish_reason="stop")])
        responses = iter([[first], [last]])
        service.client = NS(chat=NS(completions=NS(create=lambda **kw: next(responses))))
        messages = [{"role": "user", "content": "Local analysis"}]
        with Flask(__name__).app_context():
            events = list(service._run_completion(messages))
        cards = [event for event in events if event["event"] == "data_card"]
        assert bool(cards) is ok
        tool_result = json.loads(next(message["content"] for message in messages if message["role"] == "tool"))
        assert (tool_result["result_type"] != "error") is ok
        json.dumps(events, allow_nan=False)


def test_all_helpers_have_real_outputs(frames):
    for call in HELPERS:
        response = sandbox.execute_analysis(f"result={call}", frames)
        assert response["result_type"] == "table"
        assert response["rows"]


@pytest.mark.parametrize("field", ["attrs", "index_name"])
def test_series_metadata_validated_before_reset_index(field):
    class HostileMetadata(Hostile):
        def __deepcopy__(self, memo):
            raise AssertionError("metadata copy hook called")

    result = pd.Series([1])
    if field == "attrs":
        result.attrs["hostile"] = HostileMetadata()
    else:
        result.index.name = HostileMetadata()
    with pytest.raises(AnalysisRefused):
        sandbox._format_result(result)


ORDINARY = [
    ("add_prefix", "result=teams.add_prefix('club_')"),
    ("series_dot", "result=fixture_stats['goals'].dot(fixture_stats['assists'])"),
    ("numpy_trunc", "result=np.trunc([1.9,-2.9]).tolist()"),
    ("categorical_discard", "pd.Categorical(['a','b','a'])\nresult=1"),
    ("string_center", "result='club'.center(8,'.')"),
    ("string_ljust", "result='club'.ljust(8,'.')"),
    ("set_update", "values=set([1,2])\nvalues.update([2,3])\nresult=sorted(values)"),
    ("set_issubset", "result=set([1,2]).issubset(set([1,2,3]))"),
    ("column_frame", "result=int(tracked.age.mean())"),
    ("column_row", "result=fixture_stats.apply(lambda row:row.goals+row.minutes,axis=1)"),
    ("column_group", "result=fixture_stats.groupby('team_api_id').goals.sum()"),
    ("string_unique_iter", "result=[club for club in tracked['parent_club'].unique()]"),
    ("string_unique_list", "result=tracked['parent_club'].unique().tolist()"),
    ("string_values_iter", "result=[name for name in tracked['player_name'].values]"),
    ("string_values_item", "result=tracked['player_name'].values[0]"),
    ("string_numpy", "result=tracked['player_name'].unique().to_numpy().tolist()"),
    ("to_frame", "result=fixture_stats['goals'].to_frame()"),
    ("where", "result=fixture_stats[['goals']].where(fixture_stats[['goals']]>2,0)"),
    ("mask", "result=fixture_stats[['goals']].mask(fixture_stats[['goals']]>2,0)"),
    ("rolling", "result=fixture_stats['goals'].rolling(2).sum()"),
    ("expanding", "result=fixture_stats['goals'].expanding().mean()"),
    ("ffill", "result=pd.Series([1,None,3]).ffill()"),
    ("bfill", "result=pd.Series([1,None,3]).bfill()"),
    ("cumcount", "result=fixture_stats.groupby('team_api_id').cumcount()"),
    ("nth", "result=fixture_stats.groupby('team_api_id').nth(0)"),
    ("transform_rank", "result=fixture_stats.groupby('team_api_id')['goals'].transform('rank')"),
    ("transform_diff", "result=fixture_stats[['goals']].transform('diff')"),
    ("transform_shift", "result=fixture_stats[['goals']].transform('shift')"),
    ("transform_ffill", "result=fixture_stats[['goals']].transform('ffill')"),
    ("transform_bfill", "result=fixture_stats[['goals']].transform('bfill')"),
    ("transform_pct", "result=fixture_stats[['goals']].transform('pct_change')"),
    ("insert", "teams.insert(0,'new',[3,4])\nresult=teams"),
    ("sample", "result=teams.sample(n=1,random_state=5)"),
    ("filter", "result=fixture_stats.filter(like='goals')"),
    ("argmax", "result=int(fixture_stats['goals'].argmax())"),
    ("argmin", "result=int(fixture_stats['goals'].argmin())"),
    ("skew", "result=float(fixture_stats['goals'].skew())"),
    ("kurt", "result=float(fixture_stats['goals'].kurt())"),
    ("combine_first", "result=pd.Series([1,None]).combine_first(pd.Series([2,3]))"),
    ("keys", "result=teams.keys().tolist()"),
    ("group_keys", "result=[int(key) for key in fixture_stats.groupby('team_api_id').groups.keys()]"),
    ("index_names", "result=[name for name in fixture_stats.set_index('goals').index.names]"),
    ("tuple_column", "result=[row.name for row in teams.itertuples()]"),
    ("tuple_item", "result=[row[1] for row in teams.itertuples()]"),
    ("findall", "result=teams['name'].str.findall('[ae]')"),
    ("isupper", "result=teams['name'].str.isupper()"),
    ("islower", "result=teams['name'].str.islower()"),
    ("removeprefix", "result=teams['name'].str.removeprefix('A')"),
    ("removesuffix", "result=teams['name'].str.removesuffix('a')"),
    ("weekday", "result=tracked['updated_at'].dt.weekday"),
    ("to_period", "result=tracked['updated_at'].dt.to_period('M').dt.year"),
    ("tz_localize", "result=tracked['updated_at'].dt.tz_localize('UTC').dt.strftime('%Y-%m-%d')"),
    ("tz_convert", "result=tracked['updated_at'].dt.tz_localize('UTC').dt.tz_convert('Europe/London').dt.hour"),
    ("index_year", "result=pd.DatetimeIndex(tracked['updated_at']).year.tolist()"),
    ("index_get_loc", "result=int(teams.columns.get_loc('name'))"),
    ("index_difference", "result=teams.columns.difference(['name']).tolist()"),
    ("np_average", "result=float(np.average([1,2,3]))"),
    ("np_diff", "result=np.diff([1,3,6]).tolist()"),
    ("np_any", "result=bool(np.any([False,True]))"),
    ("np_all", "result=bool(np.all([True,True]))"),
    ("np_argmax", "result=int(np.argmax([1,3,2]))"),
    ("np_argmin", "result=int(np.argmin([1,3,2]))"),
    ("np_isin", "result=np.isin([1,2,3],[1,3]).tolist()"),
    ("np_nan_to_num", "result=np.nan_to_num([1,np.nan]).tolist()"),
    ("np_divide", "result=np.divide([2,4],2).tolist()"),
    ("np_corrcoef", "result=np.corrcoef([[1,2,3],[3,2,1]]).tolist()"),
    ("np_prod", "result=int(np.prod([1,2,3]))"),
    ("pd_isnull", "result=pd.isnull(pd.Series([1,None]))"),
    ("pd_notnull", "result=pd.notnull(pd.Series([1,None]))"),
    ("pd_melt", "result=pd.melt(teams,id_vars=['name'])"),
    ("pd_dummies", "result=pd.get_dummies(teams['name'],dtype=int)"),
    ("pd_date_range", "result=pd.date_range('2026-01-01',periods=3).strftime('%Y-%m-%d').tolist()"),
    ("pd_offset", "result=(pd.Timestamp('2026-01-01')+pd.DateOffset(days=2)).strftime('%Y-%m-%d')"),
    ("pd_namedagg", "result=fixture_stats.groupby('team_api_id').agg(goals=pd.NamedAgg(column='goals',aggfunc='sum'))"),
    ("pd_index", "result=pd.Index([1,2,3]).tolist()"),
    ("pd_categorical", "result=pd.Categorical(['a','b','a']).tolist()"),
    ("pd_now", "result=pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d')"),
    ("pow", "result=pow(2,3)"),
    ("divmod", "result=divmod(7,3)"),
    ("repr", "result=repr({'goals':[1,2]})"),
    ("ord", "result=ord('A')"),
    ("chr", "result=chr(65)"),
]
# The named datetime index has the same constructor-only boundary as Index.
ORDINARY = [
    (name, code.replace("pd.DatetimeIndex(tracked['updated_at'])", "pd.Index(tracked['updated_at'])"))
    for name, code in ORDINARY
]


@pytest.mark.parametrize("name,code", ORDINARY, ids=[case[0] for case in ORDINARY])
def test_ordinary_analysis_matches_main(name, code, frames):
    reference = {"pd": pd, "np": np, **{key: frame.copy(deep=True) for key, frame in frames.items()}}
    exec(code, reference)
    expected = _legacy_format_result(reference["result"])
    expected["display"] = "table"
    assert sandbox.execute_analysis(code, frames) == expected


@pytest.mark.parametrize("rows", [100_000, 200_000])
@pytest.mark.parametrize(
    "code",
    [
        "result=df",
        "result=df[df.goals>3]",
        "result=df.goals.map(lambda value:value+1)",
        "result=df.apply(lambda row:row.goals+row.minutes,axis=1)",
    ],
)
def test_production_size_analysis_matches_main(rows, code):
    frame = pd.DataFrame(
        {
            **{f"c{i}": np.arange(rows) for i in range(25)},
            "goals": np.arange(rows) % 10,
            "minutes": np.arange(rows),
            "club": pd.Series(["Club"] * rows, dtype="str"),
            "when": pd.date_range("2026-01-01", periods=rows, freq="s"),
        }
    )
    reference = {"df": frame.copy()}
    exec(code, reference)
    expected = _legacy_format_result(reference["result"])
    expected["display"] = "table"
    assert sandbox.execute_analysis(code, {"df": frame}) == expected


def test_interval_period_text_results():
    response = sandbox.execute_analysis("result=pd.cut(pd.Series([18,20,24]),bins=[17,19,21,25]).value_counts()", {})
    assert response["rows"] == [["(17, 19]", 1], ["(19, 21]", 1], ["(21, 25]", 1]]
    response = sandbox.execute_analysis("result=pd.Series(pd.date_range('2026-01-01',periods=2)).dt.to_period('M')", {})
    assert response["rows"] == [[0, "2026-01"], [1, "2026-01"]]


def test_result_string_bound():
    from src.services.gol_capabilities import MAX_STRING_CHARS

    for result in [
        "x" * (MAX_STRING_CHARS + 1),
        {"x": "x" * (MAX_STRING_CHARS + 1)},
        pd.DataFrame({"x": ["x" * (MAX_STRING_CHARS + 1)]}),
    ]:
        with pytest.raises(AnalysisSizeLimit):
            sandbox._format_result(result)


@pytest.mark.parametrize(
    "method,receiver", [(pd.DataFrame.apply, pd.DataFrame({"x": [1]})), (pd.Series.map, pd.Series([1]))]
)
def test_engine_refused_in_all_parameter_positions(method, receiver):
    import inspect

    from src.services.gol_capabilities import _safe_call

    signature = inspect.signature(method.__get__(receiver))
    params = list(signature.parameters)
    if "engine" not in params:
        pytest.skip("library version has no engine parameter")
    position = params.index("engine")
    args = [sum if param == "func" else signature.parameters[param].default for param in params[:position]]
    with pytest.raises(AnalysisRefused):
        _safe_call(method.__get__(receiver), method.__name__)(*args, engine="python")
    with pytest.raises(AnalysisRefused):
        _safe_call(method.__get__(receiver), method.__name__)(*args, "python")


def test_fixed_error_categories_and_service_hints():
    from src.services.gol_service import GolService

    categories = [
        ("result=df.missing", ERROR),
        ('result=df["missing"]', "Analysis refused: KeyError (missing column or label)."),
        ("result=)", "Analysis refused: syntax error."),
        ("import pandas", "Analysis refused: import statements are unavailable."),
        ('result="x"*10001', SIZE_ERROR),
    ]
    for code, error in categories:
        response = sandbox.execute_analysis(code, {"df": pd.DataFrame({"x": [1]})})
        assert response["error"] == error
    assert "column" in GolService._sanitize_for_llm({"error": categories[1][1]})["error"]
    assert "Import" in GolService._sanitize_for_llm({"error": categories[3][1]})["error"]
    assert "too long" in GolService._sanitize_for_llm({"error": "Analysis exceeded its execution limit."})["error"]
    assert "reduce the data scope" in GolService._sanitize_for_llm({"error": SIZE_ERROR})["error"]


# Explicit review inventory. Do not derive this table from production allowlists.
# Method-name entries can also accept restricted callables.
ATTRIBUTE_CLASSIFICATION = {
    "builtins": {
        "in-memory": "abs pow divmod ord chr all any bool dict enumerate float int isinstance len list max min range round set slice str sum tuple zip repr Exception ValueError TypeError KeyError IndexError ZeroDivisionError",
        "takes-callable": "filter map sorted",
        "takes-method-name": "",
    },
    "DataFrame": {
        "in-memory": "add_prefix combine_first T abs add all any astype at bfill clip columns copy corr count cov cummax cummin cumprod cumsum describe diff div drop drop_duplicates dropna dtypes duplicated empty eq expanding explode ffill fillna floordiv ge get gt head iat idxmax idxmin iloc index insert isin isna isnull iterrows itertuples join keys kurt le loc lt max mean median melt merge min mod mode mul ndim ne nlargest notna notnull nsmallest nunique pct_change pivot pow prod quantile rank reindex reindex_like replace reset_index rolling round sample select_dtypes set_index shape shift size skew squeeze stack std sub sum tail to_numpy transpose truediv unstack value_counts values var",
        "takes-callable": "applymap assign filter groupby map mask pipe rename rename_axis sort_index sort_values to_dict where",
        "takes-method-name": "agg aggregate apply pivot_table transform",
    },
    "Series": {
        "in-memory": "add_prefix dot combine_first T abs add all any argmax argmin astype at between bfill clip copy corr count cov cummax cummin cumprod cumsum describe diff div drop drop_duplicates dropna dt dtype duplicated empty eq expanding explode ffill fillna floordiv ge get gt head iat idxmax idxmin iloc index insert isin isna isnull items iterrows itertuples join keys kurt le loc lt max mean median melt merge min mod mode mul name ndim ne nlargest notna notnull nsmallest nunique pct_change pivot pow prod quantile rank reindex reindex_like repeat replace reset_index rolling round sample select_dtypes set_index shape shift size skew squeeze stack std str sub sum tail to_frame to_list to_numpy tolist transpose truediv unique unstack value_counts values var",
        "takes-callable": "applymap assign filter groupby map mask pipe rename rename_axis sort_index sort_values to_dict where",
        "takes-method-name": "agg aggregate apply pivot_table transform",
    },
    "Index": {
        "in-memory": "argmax argmin astype copy difference drop drop_duplicates droplevel dropna dtype duplicated empty fillna get_level_values get_loc isin isna max min name names ndim notna nunique shape size str to_list to_numpy tolist unique value_counts values",
        "takes-callable": "map rename sort_values",
        "takes-method-name": "",
    },
    "ndarray": {
        "in-memory": "T all any argmax argmin argsort astype clip copy cumprod cumsum dtype flatten item max mean min ndim prod ravel reshape round shape size sort squeeze std sum tolist transpose var",
        "takes-callable": "",
        "takes-method-name": "",
    },
    "GroupBy": {
        "in-memory": "all any bfill count cumcount cummax cummin cumprod cumsum diff ffill first get_group groups head idxmax idxmin indices kurt last max mean median min ngroups nth nunique prod quantile rank sem shift size skew std sum tail value_counts var",
        "takes-callable": "filter",
        "takes-method-name": "agg aggregate apply transform",
    },
    "StringMethods": {
        "in-memory": "capitalize casefold cat contains count endswith extract extractall find findall fullmatch get isalnum isalpha isdigit islower isnumeric isspace isupper join len lower lstrip match normalize pad partition removeprefix removesuffix repeat rfind rpartition rsplit rstrip slice slice_replace split startswith strip title upper zfill",
        "takes-callable": "replace",
        "takes-method-name": "",
    },
    "DateAccessor": {
        "in-memory": "ceil date day day_name day_of_week day_of_year dayofweek dayofyear days days_in_month daysinmonth floor hour is_leap_year is_month_end is_month_start is_quarter_end is_quarter_start is_year_end is_year_start isocalendar microsecond minute month month_name nanosecond normalize quarter round second seconds strftime time to_period total_seconds tz_convert tz_localize weekday year",
        "takes-callable": "",
        "takes-method-name": "",
    },
    "DatetimeIndex": {
        "in-memory": "argmax argmin astype ceil copy date day day_name day_of_week day_of_year dayofweek dayofyear days days_in_month daysinmonth difference drop drop_duplicates droplevel dropna dtype duplicated empty fillna floor get_level_values get_loc hour is_leap_year is_month_end is_month_start is_quarter_end is_quarter_start is_year_end is_year_start isin isna isocalendar max microsecond min minute month month_name name names nanosecond ndim normalize notna nunique quarter round second seconds shape size str strftime time to_list to_numpy to_period tolist total_seconds tz_convert tz_localize unique value_counts values weekday year",
        "takes-callable": "map rename sort_values",
        "takes-method-name": "",
    },
    "DateScalar": {
        "in-memory": "ceil date day day_name day_of_week day_of_year dayofweek dayofyear days days_in_month daysinmonth floor hour is_leap_year is_month_end is_month_start is_quarter_end is_quarter_start is_year_end is_year_start isocalendar isoformat microsecond minute month month_name nanosecond normalize quarter round second seconds strftime time to_period total_seconds tz_convert tz_localize weekday year",
        "takes-callable": "",
        "takes-method-name": "",
    },
    "Window": {
        "in-memory": "corr count cov kurt max mean median min quantile sem skew std sum var",
        "takes-callable": "",
        "takes-method-name": "agg aggregate apply",
    },
    "ExtensionArray": {
        "in-memory": "to_numpy tolist",
        "takes-callable": "",
        "takes-method-name": "",
    },
    "dtype": {
        "in-memory": "itemsize kind name",
        "takes-callable": "",
        "takes-method-name": "",
    },
    "str": {
        "in-memory": "center ljust capitalize casefold cat contains count endswith extract extractall find findall fullmatch get index isalnum isalpha isdigit islower isnumeric isspace isupper join len lower lstrip match normalize pad partition removeprefix removesuffix repeat rfind rindex rpartition rsplit rstrip slice slice_replace split splitlines startswith strip title upper zfill",
        "takes-callable": "replace",
        "takes-method-name": "",
    },
    "list-tuple": {
        "in-memory": "append clear copy count extend index insert pop remove reverse sort",
        "takes-callable": "",
        "takes-method-name": "",
    },
    "dict": {
        "in-memory": "clear copy get items keys pop setdefault update values",
        "takes-callable": "",
        "takes-method-name": "",
    },
    "set": {
        "in-memory": "add copy difference discard intersection issubset remove union update",
        "takes-callable": "",
        "takes-method-name": "",
    },
    "number": {
        "in-memory": "imag real",
        "takes-callable": "",
        "takes-method-name": "",
    },
    "numpy-number": {
        "in-memory": "imag item real",
        "takes-callable": "",
        "takes-method-name": "",
    },
    "row": {
        "in-memory": "Index club goals",
        "takes-callable": "",
        "takes-method-name": "",
    },
    "pandas-facade": {
        "in-memory": "Categorical DataFrame DateOffset Index NA NaT NamedAgg Series Timedelta Timestamp concat cut date_range get_dummies isna isnull melt merge notna notnull qcut to_datetime to_numeric to_timedelta unique",
        "takes-callable": "",
        "takes-method-name": "crosstab pivot_table",
    },
    "numpy-facade": {
        "in-memory": "where abs absolute all any arange argmax argmin argsort around array asarray average bool_ ceil clip concatenate corrcoef count_nonzero cumprod cumsum diff divide dot e exp expm1 float32 float64 floor full hstack inf int32 int64 isfinite isin isinf isnan linspace log log10 log1p log2 logical_and logical_not logical_or max maximum mean median min minimum nan nan_to_num nanmax nanmean nanmedian nanmin nanpercentile nanquantile nanstd nansum nanvar ones percentile pi power prod quantile round select sign sort sqrt square stack std sum trunc unique var vstack zeros",
        "takes-callable": "",
        "takes-method-name": "",
    },
    "timestamp-facade": {
        "in-memory": "now",
        "takes-callable": "",
        "takes-method-name": "",
    },
    "closed": {
        "in-memory": "",
        "takes-callable": "",
        "takes-method-name": "",
    },
}


def classification_receivers():
    from datetime import date, datetime, timedelta
    from types import GeneratorType

    numeric = pd.Series([1, 2], name="goals")
    text = pd.Series(["A", "b"])
    dates = pd.Series(pd.date_range("2026-01-01", periods=2))
    frame = pd.DataFrame({"goals": [1, 2], "club": ["A", "B"]})
    pandas_facade, numpy_facade = library_facades()
    receivers = [
        ("DataFrame", frame),
        ("Series", numeric),
        ("Series", text),
        ("Series", dates),
        ("Series", text.astype("category")),
        ("ndarray", np.array([1, 2])),
        ("GroupBy", frame.groupby("club")),
        ("GroupBy", numeric.groupby([1, 1])),
        ("StringMethods", text.str),
        ("DateAccessor", dates.dt),
        ("DateAccessor", pd.Series(pd.to_timedelta([1, 2], unit="D")).dt),
        ("DateAccessor", dates.dt.to_period("M").dt),
        ("DateScalar", pd.Timestamp("2026-01-01")),
        ("DateScalar", pd.Timedelta(days=1)),
        ("DateScalar", datetime(2026, 1, 1)),
        ("DateScalar", date(2026, 1, 1)),
        ("DateScalar", timedelta(days=1)),
        ("dtype", np.dtype("int64")),
        ("str", "Example"),
        ("list-tuple", []),
        ("list-tuple", ()),
        ("dict", {}),
        ("set", set()),
        ("number", 1),
        ("number", 1.0),
        ("number", True),
        ("numpy-number", np.int64(1)),
        ("numpy-number", np.float64(1)),
        ("Window", numeric.rolling(2)),
        ("Window", numeric.expanding()),
        ("row", next(frame.itertuples())),
        ("pandas-facade", pandas_facade),
        ("numpy-facade", numpy_facade),
        ("timestamp-facade", guarded_getattr(pandas_facade, "Timestamp")),
    ]
    for index in [
        pd.Index([1, 2]),
        pd.RangeIndex(2),
        pd.MultiIndex.from_tuples([(1, 2)]),
        pd.CategoricalIndex(["a"]),
        pd.IntervalIndex.from_breaks([1, 2, 3]),
        pd.period_range("2026-01-01", periods=2, freq="M"),
    ]:
        receivers.append(("Index", index))
    receivers.append(("DatetimeIndex", pd.date_range("2026-01-01", periods=2)))
    for array in [
        text.array,
        text.astype("category").array,
        dates.array,
        pd.Series(pd.to_timedelta([1, 2], unit="D")).array,
        dates.dt.to_period("M").array,
        pd.arrays.IntervalArray.from_breaks([1, 2, 3]),
        pd.array([1, None], dtype="Int64"),
        pd.array([1, None], dtype="Float64"),
        pd.array([True, None], dtype="boolean"),
    ]:
        receivers.append(("ExtensionArray", array))
    try:
        receivers.append(("ExtensionArray", pd.array(["A"], dtype="string[pyarrow]")))
    except ImportError:
        pass
    closed = [
        pd.Int64Dtype(),
        pd.StringDtype(),
        np.bool_(True),
        np.str_("A"),
        np.datetime64("2026-01-01"),
        frame.loc,
        frame.iloc,
        frame.at,
        frame.iat,
        pd.DataFrame,
        pd.Series,
        pd.Index,
        pd.Categorical,
        pd.DateOffset,
        pd.NamedAgg,
        np.int64,
        str,
        Exception,
        Exception("private"),
        lambda: 1,
        len,
        guarded_getattr(numpy_facade, "sum"),
        range(2),
        {}.keys(),
        {}.values(),
        {}.items(),
        pd.NA,
        pd.NaT,
        None,
        pd.Interval(1, 2),
        pd.Period("2026-01", freq="M"),
        slice(1),
        Decimal("6.50"),
        complex(1),
        b"data",
        frame.flags,
        pd.Series([1, 2], index=pd.date_range("2026-01-01", periods=2)).resample("D"),
        ModuleType("dummy"),
    ]
    generator = (item for item in [])
    assert isinstance(generator, GeneratorType)
    closed.append(generator)
    receivers.extend(("closed", value) for value in closed)
    return receivers


def test_every_allowed_builtin_is_classified():
    classified = set(" ".join(ATTRIBUTE_CLASSIFICATION["builtins"].values()).split())
    assert set(ALLOWED_BUILTINS) == classified


def test_every_allowed_attribute_is_classified():
    from src.services import gol_capabilities as capabilities

    # Also protect configured names absent on a particular library version.
    for key, constant in [
        ("DataFrame", "FRAME_METHODS"),
        ("Series", "SERIES_METHODS"),
        ("Index", "INDEX_METHODS"),
        ("ndarray", "ARRAY_METHODS"),
        ("GroupBy", "GROUP_METHODS"),
        ("StringMethods", "STRING_METHODS"),
        ("Window", "WINDOW_METHODS"),
        ("DateAccessor", "DATE_METHODS"),
        ("DateAccessor", "DATE_ATTRS"),
        ("pandas-facade", "PANDAS_NAMES"),
        ("numpy-facade", "NUMPY_NAMES"),
    ]:
        classified = set(" ".join(ATTRIBUTE_CLASSIFICATION[key].values()).split())
        assert set(getattr(capabilities, constant)) <= classified
    for key, receiver in classification_receivers():
        classified = set(" ".join(ATTRIBUTE_CLASSIFICATION[key].values()).split())
        candidates = set(dir(receiver)) | set(dir(type(receiver))) | classified
        if key in {"DataFrame", "Series", "GroupBy"}:
            # Existing data labels map to the same guarded item operation.
            classified |= {"goals", "club"}
            candidates |= {"goals", "club"}
        for name in candidates:
            try:
                value = guarded_getattr(receiver, name)
            except AnalysisRefused:
                continue
            assert not name.startswith("_")
            assert name in classified, (key, name)
            assert not isinstance(value, ModuleType)


def test_non_allowlisted_method_dispatch_is_refused_before_call():
    from src.services.gol_capabilities import AGGREGATIONS, TRANSFORMS, _safe_call

    calls = []

    def receiver(*args, **kwargs):
        calls.append(True)
        raise AssertionError("unvalidated dispatch reached library")

    names = {name for cls in (pd.DataFrame, pd.Series) for name in dir(cls) if not name.startswith("_")}
    for operation, allowed in [
        ("agg", AGGREGATIONS),
        ("aggregate", AGGREGATIONS),
        ("apply", AGGREGATIONS),
        ("transform", TRANSFORMS),
    ]:
        guarded = _safe_call(receiver, operation)
        for name in names - allowed:
            for spec in [name, [name], {"goals": name}, {"goals": ["sum", name]}]:
                with pytest.raises(AnalysisRefused):
                    guarded(spec)
            with pytest.raises(AnalysisRefused):
                guarded(func=name)
            if operation in {"agg", "aggregate"}:
                for spec in [("goals", name), pd.NamedAgg(column="goals", aggfunc=name)]:
                    with pytest.raises(AnalysisRefused):
                        guarded(None, label=spec)
    assert not calls


def test_property_refused_before_lookup(monkeypatch):
    frame = pd.DataFrame({"goals": [1]})
    names = {name for name in dir(pd.DataFrame) if not name.startswith("_")}
    classified = set(" ".join(ATTRIBUTE_CLASSIFICATION["DataFrame"].values()).split())
    calls = []

    def property_body(self):
        calls.append(True)
        raise AssertionError("unapproved property reached")

    for name in names - classified:
        monkeypatch.setattr(pd.DataFrame, name, property(property_body))
        with pytest.raises(AnalysisRefused):
            guarded_getattr(frame, name)
    assert not calls


def test_typed_validation_skips_cell_conversion(monkeypatch):
    from src.services import gol_capabilities as capabilities

    calls = []
    original = capabilities.plain_value

    def count(value, *args, **kwargs):
        calls.append(type(value))
        return original(value, *args, **kwargs)

    monkeypatch.setattr(capabilities, "plain_value", count)
    frame = pd.DataFrame(
        {
            "number": np.arange(100_000),
            "text": pd.Series(["Club"] * 100_000, dtype="str"),
            "date": pd.date_range("2026-01-01", periods=100_000, freq="s"),
            "category": pd.Categorical(["Club"] * 100_000),
        }
    )
    capabilities.validate_frame(frame)
    assert len(calls) < 20


@pytest.mark.parametrize("location", ["object_tail", "category", "index", "column"])
def test_dtype_validation_refuses_untrusted_values(location):
    from src.services.gol_capabilities import validate_frame

    value = Hostile()
    if location == "object_tail":
        frame = pd.DataFrame({"x": [1] * 101 + [value]})
    elif location == "category":
        frame = pd.DataFrame({"x": pd.Categorical(["a"], categories=["a", value])})
    elif location == "index":
        frame = pd.DataFrame({"x": [1]}, index=[value])
    else:
        frame = pd.DataFrame([[1]], columns=[value])
    with pytest.raises(AnalysisRefused):
        validate_frame(frame)


def test_data_label_attributes_use_item_guards():
    from src.services import gol_capabilities as capabilities

    known = set(" ".join(ATTRIBUTE_CLASSIFICATION["DataFrame"].values()).split())
    name = next(name for name in dir(pd.DataFrame) if not name.startswith("_") and name not in known)
    frame = pd.DataFrame({name: [1], "sum": [2]})
    pd.testing.assert_series_equal(guarded_getattr(frame, name), guarded_getitem(frame, name))
    assert callable(guarded_getattr(frame, "sum"))
    assert callable(guarded_getattr(frame.groupby(name), "sum"))
    with pytest.raises(AnalysisRefused):
        guarded_getattr(frame, "unknown_column_label")
    assert capabilities.FRAME_METHODS


WINDOW_CORPUS = [
    ("sum", "sum()"),
    ("mean", "mean()"),
    ("median", "median()"),
    ("min", "min()"),
    ("max", "max()"),
    ("std", "std()"),
    ("var", "var()"),
    ("count", "count()"),
    ("quantile", "quantile(0.5)"),
    ("sem", "sem()"),
    ("skew", "skew()"),
    ("kurt", "kurt()"),
    ("corr", "corr()"),
    ("cov", "cov()"),
    ("agg", "agg('sum')"),
    ("aggregate", "aggregate('sum')"),
    ("apply", "apply(lambda values:sum(values))"),
]


@pytest.mark.parametrize("window", ["rolling(5)", "expanding()"])
@pytest.mark.parametrize("name,call", WINDOW_CORPUS, ids=[case[0] for case in WINDOW_CORPUS])
def test_window_operations_match_main(window, name, call, frames):
    code = f"result=fixture_stats['goals'].{window}.{call}"
    test_ordinary_analysis_matches_main(name, code, frames)


def test_window_corpus_covers_every_allowed_method():
    from src.services.gol_capabilities import WINDOW_METHODS

    assert {name for name, call in WINDOW_CORPUS} == WINDOW_METHODS


def test_current_timestamp_without_timezone():
    response = sandbox.execute_analysis("result=pd.Timestamp.now().strftime('%Y-%m-%d')", {})
    assert response["value"] == pd.Timestamp.now().strftime("%Y-%m-%d")


def test_restricted_loop_wall_clock_deadline(monkeypatch):
    import time

    monkeypatch.setattr(sandbox, "TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(sandbox, "MAX_PYTHON_STEPS", 3_000_000)
    start = time.monotonic()
    response = sandbox.execute_analysis("while True:\n try:\n  x=1\n except Exception:\n  pass", {})
    assert response["error"] in {"Analysis exceeded its execution limit.", "Analysis timed out (10s limit)"}
    assert time.monotonic() - start < 1


DISPATCH_CLASSIFICATION = {
    "reduction": "all any count size sum mean median min max std var prod first last nunique idxmin idxmax quantile sem skew kurt cumsum cumprod cummin cummax",
    "transform": "rank diff shift pct_change ffill bfill cumcount",
}


def test_every_method_name_dispatch_is_classified():
    from src.services.gol_capabilities import AGGREGATIONS, TRANSFORMS

    assert set(DISPATCH_CLASSIFICATION["reduction"].split()) == AGGREGATIONS
    assert set(" ".join(DISPATCH_CLASSIFICATION.values()).split()) == TRANSFORMS


@pytest.mark.parametrize(
    "text,expected",
    [
        ("6.50", 6.5),
        ("6.123456", 6.1235),
        ("NaN", None),
        ("sNaN", None),
        ("Infinity", None),
        ("-Infinity", None),
        ("1e9999", None),
    ],
)
def test_decimal_plain_scalars_and_result_formatting(text, expected):
    value = Decimal(text)
    assert plain_value(value) == expected
    assert sandbox._format_result(value) == {"result_type": "scalar", "value": expected}
    assert sandbox._format_result({"rating": value})["data"] == {"rating": expected}
    frame = pd.DataFrame({"rating": pd.Series([value, None], dtype=object)})
    from src.services.gol_capabilities import validate_frame

    validate_frame(frame)
    assert sandbox.execute_analysis("result=stats", {"stats": frame})["rows"] == [[expected], [None]]


def test_decimal_input_does_not_block_other_frames(frames):
    assert frames["fixture_stats"]["decimal_rating"].dtype == object
    result = sandbox.execute_analysis("result=teams", frames)
    assert result["result_type"] == "table"
    result = sandbox.execute_analysis("result=fixture_stats['decimal_rating'].sum()", frames)
    assert result == {"result_type": "scalar", "value": 101.7, "display": "table"}


def test_decimal_subclass_is_refused():
    class CustomDecimal(Decimal):
        def __float__(self):
            raise AssertionError("custom conversion called")

    with pytest.raises(AnalysisRefused):
        plain_value(CustomDecimal("6.50"))
