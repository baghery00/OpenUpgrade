# Copyright 2020 Odoo Community Association (OCA)
# Copyright 2020 Opener B.V. <stefan@opener.am>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from openupgradelib import openupgrade

from odoo import tools

_logger = logging.getLogger(__name__)

try:
    from odoo.addons.openupgrade_scripts.apriori import merged_modules, renamed_modules
except ImportError:
    renamed_modules = {}
    merged_modules = {}
    _logger.warning(
        "You are using openupgrade_framework without having"
        " openupgrade_scripts module available."
        " The upgrade process will not work properly."
    )

module_category_xmlid_renames = [
    # Module category renames were not detected by the analyze. These records
    # are created on the fly when initializing a new database in
    # odoo/modules/db.py
    (
        "base.module_category_accounting_expenses",
        "base.module_category_human_resources_expenses",
    ),
    ("base.module_category_discuss", "base.module_category_productivity_discuss"),
    (
        "base.module_category_localization",
        "base.module_category_accounting_localizations",
    ),
    (
        "base.module_category_localization_account_charts",
        "base.module_category_accounting_localizations_account_charts",
    ),
    ("base.module_category_marketing_survey", "base.module_category_marketing_surveys"),
    (
        "base.module_category_operations_helpdesk",
        "base.module_category_services_helpdesk",
    ),
    (
        "base.module_category_operations_inventory",
        "base.module_category_inventory_inventory",
    ),
    (
        "base.module_category_operations_inventory_delivery",
        "base.module_category_inventory_delivery",
    ),
    (
        "base.module_category_operations_maintenance",
        "base.module_category_manufacturing_maintenance",
    ),
    (
        "base.module_category_operations_project",
        "base.module_category_services_project",
    ),
    (
        "base.module_category_operations_purchase",
        "base.module_category_inventory_purchase",
    ),
    (
        "base.module_category_operations_timesheets",
        "base.module_category_services_timesheets",
    ),
]


def deduplicate_ir_properties(cr):
    # delete duplicates in ir_property due to new constrain
    # see https://github.com/odoo/odoo/commit/e85faf398659a5beb0b1570a06af64dcf78dc1c8
    openupgrade.logged_query(
        cr,
        """
        DELETE FROM ir_property
        WHERE id IN (
            SELECT id
            FROM (
                SELECT id, row_number() over (
                    partition BY fields_id, company_id, res_id ORDER BY id DESC) AS rnum
                FROM ir_property
            ) t
            WHERE t.rnum > 1)""",
    )


def uninstall_conflicting_it_edi(cr):
    it_edi_conflicting_modules = ("l10n_it_edi", "l10n_it_fatturapa")
    if all(openupgrade.is_module_installed(cr, m) for m in it_edi_conflicting_modules):
        # Mark as 'to_remove' to avoid raising a conflict; it will be installed anyway,
        # but we will uninstall it for good in end-migration.
        openupgrade.logged_query(
            cr,
            """
            UPDATE ir_module_module
            SET state='to remove'
            WHERE name = 'l10n_it_edi'""",
        )


@openupgrade.migrate(use_env=False)
def migrate(cr, version):
    ############### custion scripts
    openupgrade.logged_query("""
WITH duplicates AS (
    SELECT
        id,
        ROW_NUMBER() OVER (PARTITION BY name, currency_id, company_id ORDER BY id) AS rn
    FROM
        res_currency_rate rcr 
)
DELETE FROM
    res_currency_rate 
WHERE
    id IN (
        SELECT
            id
        FROM
            duplicates
        WHERE
            rn > 1
    );

update ir_model_data set name = replace (name, ' ', '_') where name like '% %';
WITH duplicated_uom AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY category_id, uom_type ORDER BY id) AS rn
    FROM
        uom_uom rcr
    where uom_type = 'reference'
)
update uom_uom
set active = false
WHERE
    id IN (
        SELECT
            id
        FROM
            duplicated_uom
        WHERE
            rn > 1
    );
delete from utm_campaign  where stage_id in
(select res_id  from ir_model_data imd where name like 'campaign_stage_1');

delete from ir_module_module_dependency where id in (
select d.id from ir_module_module_dependency d
join ir_module_module m on m.id = d.module_id
where m.name in ('account_multicurrency_revaluation','l10n_tr_account_babs_report_xlsx', 'l10n_tr_account_eledger', 'date_range','account_check', 'account_tax_office', 'account_account_type_specifier')
and d.name = 'account_accountant'
);
update ir_module_module set state = 'to remove' where name in (
'hr_holidays_gantt_calendar', 'account_accountant', 'account_reports', 'account_type_menu', 'account_predictive_bills', 'ocn_client', 'web_diagram'
);
update account_account set user_type_id = (select res_id from ir_model_data imd where model = 'account.account.type' and name = 'data_unaffected_earnings') where code ='590000' ;
update account_account set user_type_id = (select res_id from ir_model_data imd where model = 'account.account.type' and name = 'account_type_current_pl') where code in ('591000', '690000', '692000', '697000', '698000'); 

WITH duplicates AS (
    SELECT
        id,category_id,create_date ,name,
        ROW_NUMBER() OVER (PARTITION BY category_id ,name ORDER BY id) AS rn
    FROM
        res_groups rg
)
update res_groups rg
    set name = concat(name,'_',id)
WHERE
    id IN (
        SELECT
            id
        FROM
            duplicates
        WHERE
            rn > 1
    );
update account_move_line aml
set currency_id = (select currency_id from account_move_line aml2 where aml2.move_id = aml.move_id and display_type != 'line_section' or display_type is null limit 1),
amount_currency  = 0,
credit = 0,
debit = 0,
company_id = (select company_id from account_move_line aml2 where aml2.move_id = aml.move_id and display_type != 'line_section' or display_type is null limit 1),
company_currency_id = (select company_currency_id from account_move_line aml2 where aml2.move_id = aml.move_id and display_type != 'line_section' or display_type is null limit 1)
where display_type = 'line_section';

update account_move_line l
set company_currency_id = (select currency_id from res_company co where co.id = l.company_id)
where company_currency_id is null;

update account_move_line
set amount_currency = 0
where amount_currency is null and credit=0 and debit=0;

update account_move_line
set amount_currency = case when credit > 0 then -1 * credit else debit end where (amount_currency is null or amount_currency = 0) and (credit > 0 or debit > 0);

delete from decimal_precision dp where name = 'Bank Statement Line';
delete from ir_model_data imd where res_id = 8 and model ='decimal.precision';

    """)



    ###############
    """
    Don't request an env for the base pre migration as flushing the env in
    odoo/modules/registry.py will break on the 'base' module not yet having
    been instantiated.
    """
    if "openupgrade_framework" not in tools.config["server_wide_modules"]:
        logging.error(
            "openupgrade_framework is not preloaded. You are highly "
            "recommended to run the Odoo with --load=openupgrade_framework "
            "when migrating your database."
        )
    # Rename xmlids of module categories with allow_merge
    openupgrade.rename_xmlids(cr, module_category_xmlid_renames, allow_merge=True)
    # Update ir_model_data timestamps from obsolete columns
    openupgrade.logged_query(
        cr,
        """
        UPDATE ir_model_data
        SET create_date = COALESCE(date_init, create_date),
            write_date = COALESCE(date_update, write_date)
        WHERE (create_date IS NULL OR write_date IS NULL) AND
            (date_init IS NOT NULL OR date_update IS NOT NULL)
        """,
    )
    # Set default values from odoo/addons/base/data/base_data.sql
    cr.execute(
        """ ALTER TABLE ir_model_data
        ALTER COLUMN create_date
        SET DEFAULT NOW() AT TIME ZONE 'UTC',
        ALTER COLUMN write_date
        SET DEFAULT NOW() AT TIME ZONE 'UTC'
    """
    )
    # Perform module renames and merges

    # edi_oca has been merged into oca/edi 12.0, so move the rename of edi
    # to merged in case it already exists at this point (we still need the
    # rename when migrating just a v13 db
    cr.execute("SELECT 1 FROM ir_module_module WHERE name='edi_oca'")
    if cr.fetchall():
        merged_modules["edi"] = renamed_modules.pop("edi")

    openupgrade.update_module_names(cr, renamed_modules.items())
    openupgrade.update_module_names(cr, merged_modules.items(), merge_modules=True)
    # openupgrade.clean_transient_models(cr)
    uninstall_conflicting_it_edi(cr)
    # Migrate partners from Fil to Tagalog
    # See https://github.com/odoo/odoo/commit/194ed76c5cc9
    openupgrade.logged_query(
        cr, "UPDATE res_partner SET lang = 'tl_PH' WHERE lang = 'fil_PH'"
    )
    deduplicate_ir_properties(cr)
    # Now Odoo supports disabling data exports, which is the main feature that
    # the module web_disable_export_group provided. Although the module isn't completly
    # merged into core as it allows to differentiate which type of export users can use.
    # This might be unnecessary for some module users that would drop the module while
    # others might want to keep it. To make the transition transparent for both cases,
    # we put this migration script here.
    cr.execute(
        """
            SELECT id FROM ir_model_data
            WHERE module='web_disable_export_group' AND name='group_export_data'
        """
    )
    if cr.fetchone():
        openupgrade.rename_xmlids(
            cr,
            [
                (
                    "web_disable_export_group.group_export_data",
                    "base.group_allow_export",
                )
            ],
        )
