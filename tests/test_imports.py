def test_runtime_integration_imports_resolve():
    from src.ai.matcher import get_gemini_client
    from src.core.notifier import send_whatsapp_alert
    from src.db import merge_databases, sync_all_csvs_to_db, sync_remote_git_db
    from src.generators.contacts import autonomous_contact_extraction

    assert callable(get_gemini_client)
    assert callable(send_whatsapp_alert)
    assert callable(merge_databases)
    assert callable(sync_all_csvs_to_db)
    assert callable(sync_remote_git_db)
    assert callable(autonomous_contact_extraction)
