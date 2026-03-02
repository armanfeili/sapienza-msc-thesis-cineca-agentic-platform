from src.services import tenants


def test_tenants_crud():
    # start clean
    # create
    t = tenants.create_tenant(id="t1", name="Tenant One", admin_email="a@example.com")
    assert t["id"] == "t1"
    # list
    all_t = tenants.list_tenants()
    assert any(x["id"] == "t1" for x in all_t)
    # get
    g = tenants.get_tenant("t1")
    assert g is not None and g["name"] == "Tenant One"
    # update
    tenants.update_tenant("t1", name="Tenant Uno")
    g2 = tenants.get_tenant("t1")
    assert g2["name"] == "Tenant Uno"
    # delete
    tenants.delete_tenant("t1")
    assert tenants.get_tenant("t1") is None


from src.services import tenants


def test_tenants_crud():
    # start clean
    # create
    t = tenants.create_tenant(id="t1", name="Tenant One", admin_email="a@example.com")
    assert t["id"] == "t1"
    # list
    all_t = tenants.list_tenants()
    assert any(x["id"] == "t1" for x in all_t)
    # get
    g = tenants.get_tenant("t1")
    assert g is not None and g["name"] == "Tenant One"
    # update
    tenants.update_tenant("t1", name="Tenant Uno")
    g2 = tenants.get_tenant("t1")
    assert g2["name"] == "Tenant Uno"
    # delete
    tenants.delete_tenant("t1")
    assert tenants.get_tenant("t1") is None


from src.services import tenants


def test_tenants_crud():
    # start clean
    # create
    t = tenants.create_tenant(id="t1", name="Tenant One", admin_email="a@example.com")
    assert t["id"] == "t1"
    # list
    all_t = tenants.list_tenants()
    assert any(x["id"] == "t1" for x in all_t)
    # get
    g = tenants.get_tenant("t1")
    assert g is not None and g["name"] == "Tenant One"
    # update
    tenants.update_tenant("t1", name="Tenant Uno")
    g2 = tenants.get_tenant("t1")
    assert g2["name"] == "Tenant Uno"
    # delete
    tenants.delete_tenant("t1")
    assert tenants.get_tenant("t1") is None
