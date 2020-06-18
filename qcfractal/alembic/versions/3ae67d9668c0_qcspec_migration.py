"""QCSpec Table Creation and Data Migration

Revision ID: 3ae67d9668c0
Revises: 4b27843a188a
Create Date: 2020-05-29 08:58:57.323949

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import Column, Integer, JSON, exists, and_, text, null
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import Unicode

from alembic import op


from qcfractal.storage_sockets.models import QCSpecORM, KeywordsORM, OptimizationProcedureORM
from qcfractal.interface.models import KeywordSet

# revision identifiers, used by Alembic.
revision = "3ae67d9668c0"
down_revision = "4b27843a188a"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "qc_spec",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("program", sa.String(length=100), nullable=False),
        sa.Column("basis", sa.String(length=100), nullable=True),
        sa.Column("method", sa.String(length=100), nullable=False),
        sa.Column("driver", sa.String(length=100), nullable=False),
        sa.Column("keywords", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["keywords"], ["keywords.id"],),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_unique_constraint("uix_spec", "qc_spec", ["program", "driver", "method", "basis", "keywords"])

    op.add_column("optimization_procedure", Column("qc_spec_id", Integer))
    op.create_foreign_key(
        "optimization_procedure_qc_spec_fkey",
        "optimization_procedure",
        "qc_spec",
        ["qc_spec_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("grid_optimization_procedure", Column("qc_spec_id", Integer))
    op.create_foreign_key(
        "grid_optimization_procedure_qc_spec_fkey",
        "grid_optimization_procedure",
        "qc_spec",
        ["qc_spec_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("torsiondrive_procedure", Column("qc_spec_id", Integer))
    op.create_foreign_key(
        "torsiondrive_procedure_qc_spec_fkey",
        "torsiondrive_procedure",
        "qc_spec",
        ["qc_spec_id"],
        ["id"],
        ondelete="SET NULL",
    )

    bind = op.get_bind()
    session = Session(bind=bind)

    # ----- Old Table View Definition, Required for data migration since new table
    #  definitions changed the column definition of 'qc_spec'
    optim_proc = sa.Table(
        "optimization_procedure",
        sa.MetaData(),
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("qc_spec", sa.JSON),  # Old column.
        sa.Column("qc_spec_id", sa.Integer, sa.ForeignKey("qc_spec.id")),  # New Column
    )

    grid_optim_proc = sa.Table(
        "grid_optimization_procedure",
        sa.MetaData(),
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("qc_spec", sa.JSON),  # Old column.
        sa.Column("qc_spec_id", sa.Integer, sa.ForeignKey("qc_spec.id")),  # New Column
    )

    torsiondrive_proc = sa.Table(
        "torsiondrive_procedure",
        sa.MetaData(),
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("qc_spec", sa.JSON),  # Old column
        sa.Column("qc_spec_id", sa.Integer, sa.ForeignKey("qc_spec.id")),  # New Column
    )

    # ----- Data Migration section --------
    optim_class_list = [optim_proc, grid_optim_proc, torsiondrive_proc]

    spec_id_map = {}
    # Adding the unknown keyword surrogate
    unknown_kw = KeywordsORM(**KeywordSet(values={"args": "unknown"}).dict())
    session.add(unknown_kw)
    session.commit()

    for optim_class in optim_class_list:
        qc_spec_records = session.query(optim_class.c.qc_spec.cast(JSONB)).distinct().all()

        qc_spec_list = []

        kw_map = {}
        for (spec,) in qc_spec_records:
            session.query(KeywordsORM).filter()
            try:
                keyword_id = int(spec["keywords"])
                found_id = session.query(KeywordsORM.id).filter(KeywordsORM.id == keyword_id).first()
            except ValueError as e:
                hash_index = str(spec["keywords"])
                found_id = session.query(KeywordsORM.id).filter(KeywordsORM.hash_index == hash_index).first()
            except TypeError:
                found_id = None
            finally:
                if found_id is not None:
                    kw_id = found_id[0]
                else:
                    kw_id = unknown_kw.id
                kw_map[str(spec["keywords"])] = kw_id
            if spec_id_map.get((spec["program"], spec["basis"], spec["method"], spec["driver"], kw_id)) is None:
                qcspec_obj = QCSpecORM(
                    program=spec["program"],
                    basis=spec["basis"],
                    method=spec["method"],
                    driver=spec["driver"],
                    keywords=kw_id,
                )
                qc_spec_list.append(qcspec_obj)
                spec_id_map[spec["program"], spec["basis"], spec["method"], spec["driver"], kw_id] = qcspec_obj
            session.add_all(qc_spec_list)
            session.commit()

        # Adding the reference to the new qc_spec table
        for (spec,) in qc_spec_records:
            basis, method, driver, program, keywords = (
                spec["basis"],
                spec["method"],
                spec["driver"],
                spec["program"],
                spec["keywords"],
            )
            ref_id = spec_id_map[program, basis, method, driver, kw_map[str(keywords)]].id
            # print (basis, method, driver, program, keywords, ref_id)
            from sqlalchemy.dialects import postgresql

            update_cnt = (
                session.query(optim_class)
                .filter(
                    optim_class.c.qc_spec["basis"].as_string() == basis,
                    optim_class.c.qc_spec["method"].as_string() == method,
                    optim_class.c.qc_spec["driver"].as_string() == driver,
                    optim_class.c.qc_spec["program"].as_string() == program,
                    optim_class.c.qc_spec["keywords"].as_string() == str(keywords)
                    if keywords
                    else optim_class.c.qc_spec.cast(JSONB)["keywords"].astext == null(),
                )
                .update({optim_class.c.qc_spec_id: ref_id}, synchronize_session=False)
            )
        session.commit()
    session.close()

    op.drop_column("optimization_procedure", "qc_spec")
    op.drop_column("grid_optimization_procedure", "qc_spec")
    op.drop_column("torsiondrive_procedure", "qc_spec")

    op.alter_column("optimization_procedure", "qc_spec_id", nullable=False, new_column_name="qc_spec")
    op.alter_column("grid_optimization_procedure", "qc_spec_id", nullable=False, new_column_name="qc_spec")
    op.alter_column("torsiondrive_procedure", "qc_spec_id", nullable=False, new_column_name="qc_spec")
    ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    # op.add_column("optimization_procedure", Column("qc_spec", JSON))
    bind = op.get_bind()

    op.add_column("optimization_procedure", Column("qc_spec_json", JSON))
    op.add_column("grid_optimization_procedure", Column("qc_spec_json", JSON))
    op.add_column("torsiondrive_procedure", Column("qc_spec_json", JSON))

    optim_proc = sa.Table(
        "optimization_procedure",
        sa.MetaData(),
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("qc_spec", sa.Integer, sa.ForeignKey("qc_spec.id")),  # Old column.
        sa.Column("qc_spec_json", sa.JSON),  # New Column
    )

    grid_optim_proc = sa.Table(
        "grid_optimization_procedure",
        sa.MetaData(),
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("qc_spec", sa.Integer, sa.ForeignKey("qc_spec.id")),  # Old column.
        sa.Column("qc_spec_json", sa.JSON),  # New Column
    )

    torsiondrive_proc = sa.Table(
        "torsiondrive_procedure",
        sa.MetaData(),
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("qc_spec", sa.Integer, sa.ForeignKey("qc_spec.id")),  # Old column.
        sa.Column("qc_spec_json", sa.JSON),  # New Column
    )

    session = Session(bind=bind)

    optim_class_list = [optim_proc, grid_optim_proc, torsiondrive_proc]

    for optim_class in optim_class_list:

        spec_ids = session.query(optim_class.c.qc_spec).distinct().all()

        qc_spec_entries = {}
        for (spec_id,) in spec_ids:
            if qc_spec_entries.get(spec_id):
                spec = qc_spec_entries[spec_id]
            else:
                spec = (
                    session.query(
                        QCSpecORM.basis, QCSpecORM.driver, QCSpecORM.method, QCSpecORM.program, QCSpecORM.keywords
                    )
                    .filter(QCSpecORM.id == spec_id)
                    .first()
                )
                qc_spec_entries[spec_id] = spec

            session.query(optim_class).filter(optim_class.c.qc_spec == spec_id).update(
                {
                    optim_class.c.qc_spec_json: {
                        "basis": spec.basis,
                        "driver": spec.driver,
                        "method": spec.method,
                        "program": spec.program,
                        "keywords": str(spec.keywords),
                    }
                },
                synchronize_session=False,
            )

        session.commit()
        session.close()

    op.drop_column("optimization_procedure", "qc_spec")
    op.drop_column("grid_optimization_procedure", "qc_spec")
    op.drop_column("torsiondrive_procedure", "qc_spec")

    # op.drop_constraint("optimization_procedure_qc_spec_id_fkey", "optimization_procedure", type_="foreignkey")
    # op.drop_column("optimization_procedure", "qc_spec_id")

    # op.drop_constraint("grid_optimization_procedure_qc_spec_id_fkey", "grid_optimization_procedure", type_="foreignkey")
    # op.drop_column("grid_optimization_procedure", "qc_spec_id")

    # op.drop_constraint("torsiondrive_procedure_qc_spec_id_fkey", "torsiondrive_procedure", type_="foreignkey")
    # op.drop_column("torsiondrive_procedure", "qc_spec_id")
    op.alter_column("optimization_procedure", "qc_spec_json", new_column_name="qc_spec")
    op.alter_column("grid_optimization_procedure", "qc_spec_json", new_column_name="qc_spec")
    op.alter_column("torsiondrive_procedure", "qc_spec_json", new_column_name="qc_spec")

    op.drop_table("qc_spec")

    op.execute('delete from keywords where values::jsonb = \'{"args" : "unknown"}\';')

    # ### end Alembic commands ###
