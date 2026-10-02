"""Local-only capability regression corpus; never inspect or print secrets."""

import json
from types import ModuleType

import numpy as np
import pandas as pd
import pytest
from src.services import gol_sandbox as sandbox
from src.services.gol_capabilities import (
    ALLOWED_BUILTINS,
    ERROR,
    AnalysisRefused,
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


ESCAPES = [
    ("pandas_io", "result=pd.io.common.os"),
    ("env_boolean", "result=len(pd.io.common.os.environ)>0"),
    ("system_type", "result=pd.io.common.os.system"),
    ("numpy_dict", "result=np.__dict__"),
    ("compat", "result=pd.compat"),
    ("core", "result=pd.core"),
    ("util", "result=pd.util"),
    ("api", "result=pd.api"),
    ("np_lib", "result=np.lib"),
    ("np_ctypeslib", "result=np.ctypeslib"),
    ("np_linalg", "result=np.linalg"),
    ("pickle", "result=pd.read_pickle('/tmp/sbx-pickle')"),
    ("read_file", "result=pd.read_csv('/etc/passwd')"),
    ("read_url", "result=pd.read_csv('http://127.0.0.1:9/no-request')"),
    ("read_json_url", "result=pd.read_json('http://127.0.0.1:9/no-request')"),
    ("np_load", "result=np.load('/tmp/sbx-pickle',allow_pickle=True)"),
    ("np_save", "np.save('/tmp/sbx-array',[1])\nresult=1"),
    ("np_fromfile", "result=np.fromfile('/etc/passwd')"),
    ("np_memmap", "result=np.memmap('/tmp/sbx-array')"),
    ("np_frompyfunc", "result=np.frompyfunc(str,1,1)([1])"),
    ("np_vectorize", "result=np.vectorize(str)([1])"),
    ("pd_eval", "result=pd.eval('1+1')"),
    ("df_eval", "result=teams.eval('id+1')"),
    ("df_query", "result=teams.query('@__import__(\"os\")',engine='python')"),
    ("class", "result=().__class__"),
    ("mro", "result=type(teams).mro()"),
    ("subclasses", "result=teams.__subclasses__()"),
    ("format", "result='{0.__class__}'.format(teams)"),
    ("format_map", "result='{a.__class__}'.format_map({'a':teams})"),
    ("getattr", "result=getattr(teams,'to_csv')('/tmp/sbx-file')"),
    ("vars", "result=vars(teams)"),
    ("dir", "result=dir(teams)"),
    ("globals", "result=globals()"),
    ("locals", "result=locals()"),
    ("import", "import os\nresult=1"),
    ("import_fn", "result=__import__('os')"),
    ("open", "result=open('/etc/passwd').read()"),
    ("compile", "result=compile('1','x','eval')"),
    ("setattr", "setattr(pd,'read',1)\nresult=1"),
    ("delattr", "delattr(teams,'id')\nresult=1"),
    ("class_def", "class Evil:\n pass\nresult=Evil()"),
    ("function_globals", "result=academy_comparison.__globals__"),
    ("function_closure", "result=academy_comparison.__closure__"),
    ("generator_frame", "g=(i for i in range(1))\nresult=g.gi_frame"),
    ("generator_code", "g=(i for i in range(1))\nresult=g.gi_code"),
    ("coroutine", "async def f():\n return 1\nresult=f().cr_frame"),
    ("frame_globals", "g=(i for i in range(1))\nresult=g.gi_frame.f_globals"),
    ("traceback", "try:\n 1/0\nexcept Exception as e:\n result=e.__traceback__.tb_frame"),
    ("exception_args", "result=Exception('x').args"),
    ("attrs", "result=teams.attrs"),
    ("style", "result=teams.style"),
    ("flags", "result=teams.flags"),
    ("sparse", "result=teams.sparse"),
    ("plot", "result=teams.plot"),
    ("hist", "result=teams.hist()"),
    ("indexer_obj", "result=teams.loc.obj"),
    ("groupby_obj", "result=teams.groupby('id').obj"),
    ("string_parent", "result=teams['name'].str._parent"),
    ("accessor_dict", "result=teams['name'].str.__dict__"),
    ("cat", "result=teams['name'].astype('category').cat"),
    ("df_reader", "result=pd.DataFrame.from_records('/etc/passwd')"),
    ("df_dict_reader", "result=pd.DataFrame.from_dict({'x':[1]})"),
    ("array_file", "np.array([1]).tofile('/tmp/sbx-array')\nresult=1"),
    ("array_dump", "np.array([1]).dump('/tmp/sbx-array')\nresult=1"),
    ("array_ctypes", "result=np.array([1]).ctypes"),
    ("array_interface", "result=np.array([1]).__array_interface__"),
    ("array_data", "result=np.array([1]).data"),
    ("array_base", "result=np.array([1]).base"),
    ("dtype_type", "result=np.array([1]).dtype.type.mro()"),
    ("write_method", "teams.to_csv=lambda x:1\nresult=1"),
    ("write_facade", "pd.io=1\nresult=1"),
    ("write_attrs", "teams.attrs={'x':1}\nresult=1"),
    ("dispatch_agg", "result=teams.agg('to_csv','/tmp/sbx-file')"),
    ("dispatch_apply", "result=teams.apply('to_pickle',args=('/tmp/sbx-file',))"),
    ("dispatch_transform", "result=teams.transform('eval')"),
    ("dispatch_group", "result=teams.groupby('id').agg({'name':'to_csv'})"),
    ("dispatch_named", "result=teams.groupby('id').agg(x=('name','to_csv'))"),
    ("dispatch_nested", "result=teams.agg({'name':['sum','to_csv']})"),
    ("lambda_io", "result=teams.apply(lambda x:x.to_csv('/tmp/sbx-file'))"),
    ("lambda_pipe", "result=teams.pipe(lambda x:x.eval('1'))"),
    ("lambda_map", "result=teams['name'].map(lambda x:getattr(x,'__class__'))"),
    ("engine_callable", "result=teams.apply(sum,engine=academy_comparison)"),
    ("result_function", "result=academy_comparison"),
    ("result_array", "result=np.array([1])"),
    ("result_groupby", "result=teams.groupby('id')"),
    ("nested_function", "result={'x':[academy_comparison]}"),
    ("cell_function", "result=pd.DataFrame({'x':[academy_comparison]})"),
    ("label_function", "result=pd.DataFrame([[1]],columns=[academy_comparison])"),
    ("index_function", "result=pd.Series([1],index=[academy_comparison])"),
    ("name_function", "result=pd.Series([1],name=academy_comparison)"),
    ("result_exception", "result=Exception('do not echo')"),
    ("cycle", "a=[]\na.append(a)\nresult=a"),
    ("helper_callable", "result=player_career(str)"),
    ("getitem_facade", "result=pd['io']"),
]
for receiver in ("teams", "teams['name']", "teams.index"):
    for method in (
        "to_csv",
        "to_pickle",
        "to_sql",
        "to_parquet",
        "to_hdf",
        "to_excel",
        "to_json",
        "to_clipboard",
        "to_feather",
        "to_html",
        "to_xml",
        "to_latex",
        "to_string",
        "to_markdown",
        "eval",
        "query",
    ):
        ESCAPES.append((f"writer_{receiver}_{method}", f"result={receiver}.{method}('/tmp/sbx-file')"))
for method in ("to_csv", "to_pickle", "to_json", "eval", "query"):
    ESCAPES.append(
        (f"pivot_dispatch_{method}", f"result=teams.pivot_table(index='id',values='name',aggfunc='{method}')")
    )


ESCAPES += [
    ("agg_none_positional", "result=teams.groupby('id').agg(None,x=('name','to_csv'))"),
    ("agg_none_keyword", "result=teams.groupby('id').agg(func=None,x=('name','to_csv'))"),
    ("pivot_positional", "result=teams.pivot_table('name','id',None,'to_csv')"),
    ("pd_pivot_positional", "result=pd.pivot_table(teams,'name','id',None,'to_csv')"),
    ("crosstab_positional", "result=pd.crosstab(teams['id'],teams['name'],teams['id'],None,None,'to_csv')"),
    ("timezone_file", "result=pd.Timestamp('2026-01-01',tz='dateutil//etc/passwd')"),
    (
        "timezone_file_positional",
        "result=pd.Timestamp('2026-01-01',None,None,None,None,None,None,None,'dateutil//etc/passwd')",
    ),
    ("function_kwdefaults", "result=academy_comparison.__kwdefaults__"),
    ("ufunc_attrs", "result=np.sum.__globals__"),
    ("ndarray_dtype_mro", "result=np.int64.mro()"),
    ("class_method", "result=pd.Series.mro()"),
    ("builtin_format", "result=format(teams,'')"),
    ("getattribute", "result=teams.__getattribute__('to_csv')"),
    ("dict_key_callable", "result={academy_comparison:1}"),
    ("series_function", "result=pd.Series([academy_comparison])"),
    ("accessor_lambda", "result=teams['name'].str.replace('a',lambda x:x.__class__)"),
    ("dt_parent", "result=pd.to_datetime(teams['id']).dt._parent"),
    ("dt_tz", "result=pd.to_datetime(teams['id']).dt.tz"),
    ("array_dumps", "result=np.array([1]).dumps()"),
    ("array_getfield", "result=np.array([1]).getfield('int64')"),
    ("bare_handler", "try:\n result=1\nexcept:\n result=2"),
    ("finally", "try:\n result=1\nfinally:\n result=2"),
]


@pytest.mark.parametrize("name,code", ESCAPES, ids=[case[0] for case in ESCAPES])
def test_escape_is_neutrally_refused_before_io(name, code, frames, monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("unexpected I/O entry point")

    for module, names in (
        (pd, ["read_csv", "read_json", "read_pickle", "eval"]),
        (np, ["load", "save", "fromfile", "memmap"]),
    ):
        for method in names:
            monkeypatch.setattr(module, method, forbidden)
    for cls in (pd.DataFrame, pd.Series):
        for method in (
            "to_csv",
            "to_pickle",
            "to_sql",
            "to_parquet",
            "to_hdf",
            "to_excel",
            "to_json",
            "to_clipboard",
            "to_feather",
            "to_html",
            "to_xml",
            "to_latex",
            "to_string",
            "to_markdown",
            "eval",
            "query",
        ):
            if hasattr(cls, method):
                monkeypatch.setattr(cls, method, forbidden)
    response = sandbox.execute_analysis(code, frames)
    assert response == {"result_type": "error", "error": ERROR, "display": "table"}
    assert not calls


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
    assert sandbox.execute_analysis("result=np.zeros((1000001,))", {})["error"] == ERROR
    assert not calls


def test_compilation_bound():
    assert sandbox.execute_analysis("x=1\n" * 6000, {})["error"] == ERROR


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


@pytest.mark.parametrize("code", [123, ["result=1"], "result=)", 'result=df["private-column-label"]'])
def test_invalid_code_and_errors_do_not_echo_details(code):
    response = sandbox.execute_analysis(code, {"df": pd.DataFrame({"x": [1]})})
    assert response == {"result_type": "error", "error": ERROR, "display": "table"}


def test_large_dtype_is_refused_before_allocation(monkeypatch):
    calls = []
    monkeypatch.setattr(np, "zeros", lambda *a, **kw: calls.append(True))
    response = sandbox.execute_analysis("result=np.zeros(1,dtype='U100000000')", {})
    assert response["error"] == ERROR
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
        ("result=pd.io", False),
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
