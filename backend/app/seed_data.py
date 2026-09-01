KNN_DRAFT = {
    "schema_version": "ProblemDraftV1",
    "title": "从零实现 KNN 分类器",
    "slug_hint": "knn-classifier-from-scratch",
    "description": """给定训练样本、训练标签和待预测样本，请实现 K 近邻（KNN）分类器。

对每个待预测样本计算它与全部训练样本的欧氏距离，选择距离最近的 k 个邻居，并返回出现次数最多的标签。若多个标签票数相同，返回数值较小的标签。

NumPy 已经以 `np` 提供，无需也不能编写 import 语句。""",
    "difficulty": "easy",
    "tags": ["KNN", "分类", "距离度量"],
    "constraints": [
        "1 ≤ k ≤ 训练样本数",
        "训练集和测试集的特征维度相同",
        "标签为整数",
        "距离相同时按训练样本原始顺序选择邻居",
    ],
    "function_spec": {
        "class_name": "Solution",
        "method_name": "predict",
        "args": [
            {"name": "X_train", "type": "ndarray", "description": "训练特征"},
            {"name": "y_train", "type": "ndarray", "description": "训练标签"},
            {"name": "X_test", "type": "ndarray", "description": "待预测特征"},
            {"name": "k", "type": "int", "description": "邻居数量"},
        ],
        "return_type": "list",
    },
    "starter_code": """class Solution:
    def predict(self, X_train, y_train, X_test, k):
        # NumPy 已通过 np 提供
        # 在这里实现 KNN，并返回 Python list
        pass
""",
    "public_cases": [
        {
            "name": "基础二分类",
            "args": {
                "X_train": [[0, 0], [1, 1], [5, 5], [6, 6]],
                "y_train": [0, 0, 1, 1],
                "X_test": [[0.5, 0.5], [5.5, 5.5]],
                "k": 3,
            },
            "expected": [0, 1],
        }
    ],
    "hidden_cases": [
        {
            "name": "单个邻居",
            "args": {
                "X_train": [[0], [2], [10]],
                "y_train": [3, 4, 9],
                "X_test": [[1.8], [8]],
                "k": 1,
            },
            "expected": [4, 9],
        },
        {
            "name": "投票平局选择较小标签",
            "args": {
                "X_train": [[0], [2], [4], [6]],
                "y_train": [2, 1, 2, 1],
                "X_test": [[3]],
                "k": 4,
            },
            "expected": [1],
        },
        {
            "name": "重复样本",
            "args": {
                "X_train": [[1, 1], [1, 1], [3, 3]],
                "y_train": [5, 5, 8],
                "X_test": [[1, 1]],
                "k": 2,
            },
            "expected": [5],
        },
    ],
    "checker": {"kind": "exact", "atol": 0, "rtol": 0, "threshold": None},
    "resource_limits": {"timeout_seconds": 3, "memory_mb": 256, "output_kb": 32},
    "reference_solution": """class Solution:
    def predict(self, X_train, y_train, X_test, k):
        predictions = []
        for sample in X_test:
            distances = np.sqrt(np.sum((X_train - sample) ** 2, axis=1))
            neighbors = np.argsort(distances, kind="stable")[:k]
            labels, counts = np.unique(y_train[neighbors], return_counts=True)
            max_count = np.max(counts)
            predictions.append(int(np.min(labels[counts == max_count])))
        return predictions
""",
    "mutants": [
        """class Solution:
    def predict(self, X_train, y_train, X_test, k):
        return [int(y_train[0]) for sample in X_test]
""",
        """class Solution:
    def predict(self, X_train, y_train, X_test, k):
        result = []
        for sample in X_test:
            distances = np.sum((X_train - sample) ** 2, axis=1)
            result.append(int(y_train[np.argmax(distances)]))
        return result
""",
    ],
}


KMEANS_DRAFT = {
    "schema_version": "ProblemDraftV1",
    "title": "实现确定性 K-Means 聚类",
    "slug_hint": "deterministic-kmeans",
    "description": """实现一个确定性的 K-Means 聚类算法。

初始中心固定为输入中的前 k 个样本。每轮先把样本分配给欧氏距离平方最小的中心，再将中心更新为簇内样本均值；距离相同时选择编号较小的簇。若某个簇为空，保留它上一轮的中心。标签不再变化或达到最大轮数时停止，返回每个输入样本的簇标签。

判题会忽略簇编号本身，只比较样本间的聚类划分是否等价。NumPy 已通过 `np` 提供。""",
    "difficulty": "medium",
    "tags": ["K-Means", "聚类", "迭代优化"],
    "constraints": [
        "1 ≤ k ≤ 样本数",
        "1 ≤ max_iters ≤ 1000",
        "输入为有限浮点数",
        "空簇保留上一轮中心",
    ],
    "function_spec": {
        "class_name": "Solution",
        "method_name": "fit_predict",
        "args": [
            {"name": "X", "type": "ndarray", "description": "二维样本矩阵"},
            {"name": "k", "type": "int", "description": "簇数量"},
            {"name": "max_iters", "type": "int", "description": "最大迭代次数"},
        ],
        "return_type": "list",
    },
    "starter_code": """class Solution:
    def fit_predict(self, X, k, max_iters):
        # 初始中心使用 X 的前 k 行
        # 返回长度为 len(X) 的标签 list
        pass
""",
    "public_cases": [
        {
            "name": "两个清晰簇",
            "args": {"X": [[0, 0], [0, 1], [9, 9], [9, 8]], "k": 2, "max_iters": 100},
            "expected": [0, 0, 1, 1],
        }
    ],
    "hidden_cases": [
        {
            "name": "一维三簇",
            "args": {"X": [[0], [10], [20], [1], [11], [21]], "k": 3, "max_iters": 100},
            "expected": [0, 1, 2, 0, 1, 2],
        },
        {
            "name": "重复样本",
            "args": {"X": [[1, 1], [8, 8], [1, 1], [9, 9]], "k": 2, "max_iters": 20},
            "expected": [0, 1, 0, 1],
        },
        {
            "name": "最大轮数为一",
            "args": {"X": [[0], [5], [9]], "k": 2, "max_iters": 1},
            "expected": [0, 1, 1],
        },
    ],
    "checker": {
        "kind": "labels_equivalent",
        "atol": 0,
        "rtol": 0,
        "threshold": None,
    },
    "resource_limits": {"timeout_seconds": 3, "memory_mb": 256, "output_kb": 32},
    "reference_solution": """class Solution:
    def fit_predict(self, X, k, max_iters):
        X = np.asarray(X, dtype=float)
        centers = X[:k].copy()
        labels = np.full(len(X), -1, dtype=int)
        for step in range(max_iters):
            distances = np.sum((X[:, None, :] - centers[None, :, :]) ** 2, axis=2)
            new_labels = np.argmin(distances, axis=1)
            if np.array_equal(labels, new_labels):
                break
            labels = new_labels
            for cluster in range(k):
                members = X[labels == cluster]
                if len(members) > 0:
                    centers[cluster] = np.mean(members, axis=0)
        return labels.tolist()
""",
    "mutants": [
        """class Solution:
    def fit_predict(self, X, k, max_iters):
        return [0 for sample in X]
""",
        """class Solution:
    def fit_predict(self, X, k, max_iters):
        return [index % k for index in range(len(X))]
""",
    ],
}


SEED_DRAFTS = [KNN_DRAFT, KMEANS_DRAFT]

