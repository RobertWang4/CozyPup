from app.rag.intent import needs_retrieval


class TestNeedsRetrieval:
    # Recording actions — should NOT need retrieval
    def test_skip_feeding_record(self):
        assert needs_retrieval("豆豆今天吃了200克狗粮") is False

    def test_skip_vaccine_record(self):
        assert needs_retrieval("今天打了疫苗") is False

    def test_skip_vet_appointment(self):
        assert needs_retrieval("维尼明天要去看医生") is False

    def test_skip_walk_record(self):
        assert needs_retrieval("遛狗了") is False

    def test_skip_fed(self):
        assert needs_retrieval("fed Buddy 200g kibble") is False

    # Questions — SHOULD need retrieval
    def test_question_mark_zh(self):
        assert needs_retrieval("豆豆上次打疫苗是什么时候？") is True

    def test_question_mark_en(self):
        assert needs_retrieval("When was Buddy's last vaccine?") is True

    def test_how_question(self):
        assert needs_retrieval("豆豆最近怎么样") is True

    def test_history_query(self):
        assert needs_retrieval("看看豆豆的历史记录") is True

    def test_last_time_query(self):
        assert needs_retrieval("上次吃了多少") is True

    def test_why_question(self):
        assert needs_retrieval("为什么豆豆会吐") is True

    # Ambiguous — default to retrieval
    def test_ambiguous_defaults_to_retrieval(self):
        assert needs_retrieval("你好") is True

    def test_general_chat(self):
        assert needs_retrieval("Golden Retrievers are what size?") is True

    # Recording + question combined — should retrieve
    def test_recording_with_question(self):
        assert needs_retrieval("今天吃了200克，这够吗？") is True

    def test_feeding_with_how_much(self):
        assert needs_retrieval("喂了多少") is True
