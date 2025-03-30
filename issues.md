# Issues

1. Nested ObservableValue 內層修改不會更新
    ```python
    from sizekick import Viz, ObservableValue
    v = Viz()
    d = ObservableValue({"a": 1, "b": 2})
    v.show("d", d)
    d["a"] = ObservableValue([1, 2, 3])
    d["a"][0] = 4 # 這行不會更新
    ```
2. Canvas 要如何設定 stroke_style 等等

