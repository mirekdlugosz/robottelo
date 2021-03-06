"""Test class for Foreman Templates Import Export from API

:Requirement: TemplatesPlugin

:CaseAutomation: Automated

:CaseLevel: Integration

:CaseComponent: TemplatesPlugin

:TestType: Functional

:Upstream: No
"""
import time

import pytest
from fauxfactory import gen_string
from nailgun import entities
from requests import get
from requests.exceptions import HTTPError

from robottelo import ssh
from robottelo.constants import FOREMAN_TEMPLATE_IMPORT_URL
from robottelo.constants import FOREMAN_TEMPLATE_ROOT_DIR
from robottelo.constants import FOREMAN_TEMPLATE_TEST_TEMPLATE
from robottelo.constants import FOREMAN_TEMPLATES_COMMUNITY_URL


class TestTemplateSyncTestCase:
    """Implements TemplateSync tests from API

    :CaseComponent: TemplatesPlugin

    :CaseLevel: Acceptance
    """

    @pytest.fixture(scope='module', autouse=True)
    def setUpClass(self):
        """Setup for TemplateSync functional testing

        :setup:

            1. Check if the the foreman templates custom repo and community templates repo is
            accessible.
            2. Download the example template in test running root dir to be used by tests

        Information:
            - https://theforeman.org/plugins/foreman_templates/5.0/index.html
            - /apidoc/v2/template/import.html
            - /apidoc/v2/template/export.html
            - http://pastebin.test.redhat.com/516304

        """
        # Check all Downloadable templates exists
        if get(FOREMAN_TEMPLATE_IMPORT_URL).status_code != 200:
            raise HTTPError('The foreman templates git url is not accessible')
        if get(FOREMAN_TEMPLATES_COMMUNITY_URL).status_code != 200:
            raise HTTPError('The foreman templates git url is not accessible')

        # Download the Test Template in test running folder
        ssh.command(f'[ -f example_template.erb ] || wget {FOREMAN_TEMPLATE_TEST_TEMPLATE}')

    @pytest.mark.tier2
    def test_positive_import_filtered_templates_from_git(self, module_org, module_location):
        """Assure only templates with a given filter regex are pulled from
        git repo.

        :id: 628a95d6-7a4e-4e56-ad7b-d9fecd34f765

        :Steps:
            1. Using nailgun or direct API call
               import only the templates matching with regex e.g: `^atomic.*`
               refer to: `/apidoc/v2/template/import.html`

        :expectedresults:
            1. Assert result is {'message': 'success'} and template imported
            2. Assert no other template has been imported but only those
               matching specified regex.
               NOTE: Templates are always imported with a prefix defaults to
               `community` unless it is specified as empty string
            3. Assert json output doesnt have
               'Name is not matching filter condition, skipping' info message
               for imported template

        :CaseImportance: High
        """
        prefix = gen_string('alpha')
        filtered_imported_templates = entities.Template().imports(
            data={
                'repo': FOREMAN_TEMPLATE_IMPORT_URL,
                'branch': 'automation',
                'filter': 'robottelo',
                'organization_ids': [module_org.id],
                'location_ids': [module_location.id],
                'prefix': prefix,
            }
        )
        imported_count = [
            template['imported']
            for template in filtered_imported_templates['message']['templates']
        ].count(True)
        assert imported_count == 8
        ptemplates = entities.ProvisioningTemplate().search(
            query={
                'per_page': '100',
                'search': f'name~{prefix}',
                'organization_id': module_org.id,
                'location_id': module_location.id,
            }
        )
        assert len(ptemplates) == 5
        ptables = entities.PartitionTable().search(
            query={
                'per_page': '100',
                'search': f'name~{prefix}',
                'organization_id': module_org.id,
                'location_id': module_location.id,
            }
        )
        assert len(ptables) == 1
        jtemplates = entities.JobTemplate().search(
            query={
                'per_page': '100',
                'search': f'name~{prefix}',
                'organization_id': module_org.id,
                'location_id': module_location.id,
            }
        )
        assert len(jtemplates) == 1
        rtemplates = entities.ReportTemplate().search(
            query={
                'per_page': '10',
                'search': f'name~{prefix}',
                'organization_id': module_org.id,
                'location_id': module_location.id,
            }
        )
        assert len(rtemplates) == 1

    @pytest.mark.tier2
    def test_import_filtered_templates_from_git_with_negate(self, module_org):
        """Assure templates with a given filter regex are NOT pulled from
        git repo.

        :id: a6857454-249b-4a2e-9b53-b5d7b4eb34e3

        :Steps:
            1. Using nailgun or direct API call
               import the templates NOT matching with regex e.g: `^freebsd.*`
               refer to: `/apidoc/v2/template/import.html` using the
               {'negate': true} in POST body to negate the filter regex.

        :expectedresults:
            1. Assert result is {'message': 'success'}
            2. Assert templates mathing the regex were not pulled.

        :CaseImportance: Medium
        """
        prefix = gen_string('alpha')
        filtered_imported_templates = entities.Template().imports(
            data={
                'repo': FOREMAN_TEMPLATE_IMPORT_URL,
                'branch': 'automation',
                'filter': 'robottelo',
                'organization_ids': [module_org.id],
                'prefix': prefix,
                'negate': True,
            }
        )
        not_imported_count = [
            template['imported']
            for template in filtered_imported_templates['message']['templates']
        ].count(False)
        assert not_imported_count == 8
        ptemplates = entities.ProvisioningTemplate().search(
            query={'per_page': '100', 'search': 'name~jenkins', 'organization_id': module_org.id}
        )
        assert len(ptemplates) == 6
        ptables = entities.PartitionTable().search(
            query={'per_page': '100', 'search': 'name~jenkins', 'organization_id': module_org.id}
        )
        assert len(ptables) == 1
        jtemplates = entities.JobTemplate().search(
            query={'per_page': '100', 'search': 'name~jenkins', 'organization_id': module_org.id}
        )
        assert len(jtemplates) == 1
        rtemplates = entities.ReportTemplate().search(
            query={'per_page': '100', 'search': 'name~jenkins', 'organization_id': module_org.id}
        )
        assert len(rtemplates) == 1

    @pytest.mark.tier2
    def test_positive_import_and_associate(
        self,
        create_import_export_local_dir,
        module_location,
        module_org,
        default_org,
        default_location,
    ):
        """Assure imported templates are associated/not_associated with taxonomies based on
        `associate` option and templates metadata.

        :id: 04a14a56-bd71-412b-b2da-4b8c3991c401

        :Steps:
            1. Create new taxonomies, lets say org X and loc Y.
            2. From X and Y taxonomies scope, Import template1 as associate 'never', where the
                template contains the metadata anything other than X and Y taxonomies.
            3. Create new template2 in the importing source.
            4. From X and Y taxonomies scope, Import template 1 and 2 as associate 'new',
                where the template contains the metadata anything other than X and Y taxonomies.
            5. From X and Y taxonomies scope, Import template 1 and 2 as associate 'always',
                where the template contains the metadata anything other than X and Y taxonomies.

        :expectedresults:
            1. with Associate Never, templates are imported in importing taxonomies
            2. with Associate Never, templates are not imported in metadata taxonomies
            3. with Associate New, on reimporting the existing templates, taxonomies
                are not changed to metadata taxonomies
            4. with Associate New, new templates are imported in importing taxonomies
                even though importing taxonomies are not part of metadata taxonomies
            5. with Associate Always, all the existing and new templates are imported in importing
                taxonomies even though importing taxonomies are not part of metadata taxonomies

        :CaseImportance: Medium
        """
        prefix = gen_string('alpha')
        _, dir_path = create_import_export_local_dir
        # Associate Never
        entities.Template().imports(
            data={
                'repo': dir_path,
                'prefix': prefix,
                'organization_ids': [module_org.id],
                'location_ids': [module_location.id],
                'associate': 'never',
            }
        )
        # - Template 1 imported in X and Y taxonomies
        ptemplate = entities.ProvisioningTemplate().search(
            query={
                'per_page': '10',
                'search': f'name~{prefix}',
                'organization_id': module_org.id,
                'location_id': module_location.id,
            }
        )
        assert ptemplate
        assert len(ptemplate[0].read().organization) == 1
        # - Template 1 not imported in metadata taxonomies
        ptemplate = entities.ProvisioningTemplate().search(
            query={
                'per_page': '10',
                'search': f'name~{prefix}',
                'organization_id': default_org.id,
                'location_id': default_location.id,
            }
        )
        assert not ptemplate
        # Associate New
        ssh.command(
            f'cp {dir_path}/example_template.erb {dir_path}/another_template.erb && '
            f'sed -ie "s/name: .*/name: another_template/" {dir_path}/another_template.erb'
        )
        entities.Template().imports(
            data={
                'repo': dir_path,
                'prefix': prefix,
                'organization_ids': [module_org.id],
                'location_ids': [module_location.id],
                'associate': 'new',
            }
        )
        # - Template 1 taxonomies are not changed
        ptemplate = entities.ProvisioningTemplate().search(
            query={
                'per_page': '10',
                'search': f'name~{prefix}example_template',
                'organization_id': module_org.id,
                'location_id': module_location.id,
            }
        )
        assert ptemplate
        assert len(ptemplate[0].read().organization) == 1
        # - Template 2 should be imported in importing taxonomies
        ptemplate = entities.ProvisioningTemplate().search(
            query={
                'per_page': '10',
                'search': f'name~{prefix}another_template',
                'organization_id': module_org.id,
                'location_id': module_location.id,
            }
        )
        assert ptemplate
        assert len(ptemplate[0].read().organization) == 1
        # Associate Always
        entities.Template().imports(
            data={
                'repo': dir_path,
                'prefix': prefix,
                'organization_ids': [module_org.id],
                'location_ids': [module_location.id],
                'associate': 'always',
            }
        )
        # - Template 1 taxonomies are not changed
        ptemplate = entities.ProvisioningTemplate().search(
            query={
                'per_page': '10',
                'search': f'name~{prefix}example_template',
                'organization_id': module_org.id,
                'location_id': module_location.id,
            }
        )
        assert ptemplate
        assert len(ptemplate[0].read().organization) == 1
        # - Template 2 taxonomies are not changed
        ptemplate = entities.ProvisioningTemplate().search(
            query={
                'per_page': '10',
                'search': f'name~{prefix}another_template',
                'organization_id': module_org.id,
                'location_id': module_location.id,
            }
        )
        assert ptemplate
        assert len(ptemplate[0].read().organization) == 1

    @pytest.mark.tier2
    def test_positive_import_to_subdirectory(self, module_org):
        """Assure templates are imported from specific repositories subdirectory

        :id: 8ea11a1a-165e-4834-9387-7accb4c94e77

        :Steps:
            1. Using nailgun or direct API call
               import templates specifying a git subdirectory e.g:
               `-d {'dirname': 'test_sub_dir'}` in POST body

        :expectedresults:
            1. Assert result is {'message': 'success'} and templates imported
            2. Assert templates are imported only from given subdirectory

        :CaseImportance: Medium
        """
        prefix = gen_string('alpha')
        filtered_imported_templates = entities.Template().imports(
            data={
                'repo': FOREMAN_TEMPLATE_IMPORT_URL,
                'branch': 'automation',
                'dirname': 'from_dir/inside_dir',
                'organization_ids': [module_org.id],
                'prefix': prefix,
            }
        )
        imported_count = [
            template['imported']
            for template in filtered_imported_templates['message']['templates']
        ].count(True)
        # check name of imported temp
        assert imported_count == 1

    @pytest.mark.tier2
    def test_positive_import_community_templates_from_repo(self, module_org):
        """Assure all community templates are imported if no filter is specified.

        :id: 95ac9543-d989-44f4-b4d9-18f20a0b58b9

        :Steps:
            1. Using nailgun or direct API call
               import all community templates from repository (ensure filters are empty)

        :expectedresults:
            1. Assert result is {'message': 'success'}
            2. Assert all community templates are imported.

        :CaseImportance: Low
        """
        filtered_imported_templates = entities.Template().imports(
            data={
                'repo': FOREMAN_TEMPLATES_COMMUNITY_URL,
                'associate': 'always',
                'organization_ids': [module_org.id],
            }
        )
        imported_count = [
            template['imported']
            for template in filtered_imported_templates['message']['templates']
        ].count(True)
        assert imported_count > 150

    # Export tests

    @pytest.mark.tier2
    def test_positive_export_filtered_templates_to_localdir(
        self, module_org, create_import_export_local_dir
    ):
        """Assure only templates with a given filter regex are pushed to
        local directory (new templates are created, existing updated).

        :id: b7c98b75-4dd1-4b6a-b424-35b0f48c25db

        :Steps:
            1. Using nailgun or direct API call
               export only the templates matching with regex e.g: `robottelo`
               refer to: `/apidoc/v2/template/export.html`

        :expectedresults:
            1. Assert result is {'message': 'success'} and templates exported.
            2. Assert no other template has been exported but only those
               matching specified regex.

        :CaseImportance: Low
        """
        dir_name, dir_path = create_import_export_local_dir
        exported_temps = entities.Template().exports(
            data={
                'repo': FOREMAN_TEMPLATE_ROOT_DIR,
                'dirname': dir_name,
                'organization_ids': [module_org.id],
                'filter': 'ansible',
            }
        )
        exported_count = [
            template['exported'] for template in exported_temps['message']['templates']
        ].count(True)
        assert exported_count == 23
        assert ssh.command(f'find {dir_path} -type f -name *ansible* | wc -l').stdout[0] == '23'

    @pytest.mark.tier2
    def test_positive_export_filtered_templates_negate(
        self, module_org, create_import_export_local_dir
    ):
        """Assure templates with a given filter regex are not exported.

        :id: 2f8ad8f3-f02b-4b2d-85af-423a228976f3

        :Steps:
            1. Using nailgun or direct API call
               export templates matching that does not matches regex e.g: `robottelo`
               using `negate` option.


        :expectedresults:
            1. Assert templates other than `robottelo` has been exported.

        :CaseImportance: Medium
        """
        # Export some filtered templates to local dir
        dir_name, dir_path = create_import_export_local_dir
        entities.Template().exports(
            data={
                'repo': dir_path,
                'organization_ids': [module_org.id],
                'filter': 'ansible',
                'negate': True,
            }
        )
        assert ssh.command(f'find {dir_path} -type f -name *ansible* | wc -l').stdout[0] == '0'
        assert ssh.command(f'find {dir_path} -type f | wc -l').stdout[0] != '0'

    @pytest.mark.tier2
    def test_positive_export_and_import_with_metadata(
        self, create_import_export_local_dir, module_org, module_location
    ):
        """Assure exported template contains metadata.

        :id: ba8a34ce-c2c6-4889-8729-59714c0a4b19

        :Steps:
            1. Create a template in local directory and specify Org/Loc.
            2. Use import to pull this specific template (using filter).
            3. Using nailgun or direct API call
               export the template containing metadata with Org/Loc specs
               and specify the `metadata_export_mode` parameter
               e.g: `-d {'metadata_export_mode': 'refresh'}` in POST body

        :expectedresults:
            1. Assert template is exported and new org/loc are present on
               template metadata

        :CaseImportance: Medium
        """
        ex_template = 'example_template.erb'
        prefix = gen_string('alpha')
        _, dir_path = create_import_export_local_dir
        entities.Template().imports(
            data={
                'repo': dir_path,
                'location_ids': [module_location.id],
                'organization_ids': [module_org.id],
                'prefix': prefix,
            }
        )
        export_file = f'{prefix.lower()}{ex_template}'
        # Export same template to local dir with refreshed metadata
        entities.Template().exports(
            data={
                'metadata_export_mode': 'refresh',
                'repo': dir_path,
                'location_ids': [module_location.id],
                'organization_ids': [module_org.id],
                'filter': prefix,
            }
        )
        result = ssh.command(
            f'grep {module_org.name} {dir_path}/provisioning_templates/user_data/{export_file}'
        )
        assert result.return_code == 0
        # Export same template to local dir with keeping metadata
        entities.Template().exports(
            data={
                'metadata_export_mode': 'keep',
                'repo': dir_path,
                'organization_ids': [module_org.id],
                'location_ids': [module_location.id],
                'filter': prefix,
            }
        )
        result = ssh.command(
            f'grep {module_org.name} {dir_path}/provisioning_templates/user_data/{export_file}'
        )
        assert result.return_code == 1
        # Export same template to local dir with removed metadata
        entities.Template().exports(
            data={
                'metadata_export_mode': 'remove',
                'repo': dir_path,
                'organization_ids': [module_org.id],
                'location_ids': [module_location.id],
                'filter': prefix,
            }
        )
        result = ssh.command(
            f'grep organizations: {dir_path}/provisioning_templates/user_data/{export_file}'
        )
        assert result.return_code == 1

    # Take Templates out of Tech Preview Feature Tests
    @pytest.mark.tier3
    def test_positive_import_json_output_verbose_true(self, module_org):
        """Assert all the required fields displayed in import output when
        verbose is True

        :id: 74b0a701-341f-4062-9769-e5cb1a1c4792

        :Steps:
            1. Using nailgun or direct API call
               Impot a template with verbose `True` option

        :expectedresults:
            1. Assert json output has all the following fields
               'name', 'imported', 'diff', 'additional_errors', 'exception',
               'validation_errors', 'file'

        :Requirement: Take Templates out of tech preview

        :CaseImportance: Low
        """
        prefix = gen_string('alpha')
        templates = entities.Template().imports(
            data={
                'repo': FOREMAN_TEMPLATE_IMPORT_URL,
                'branch': 'master',
                'filter': 'robottelo',
                'organization_ids': [module_org.id],
                'prefix': prefix,
                'verbose': True,
            }
        )
        expected_fields = [
            'name',
            'imported',
            'diff',
            'additional_errors',
            'exception',
            'validation_errors',
            'file',
            'type',
            'id',
            'changed',
            'additional_info',
        ]
        actual_fields = templates['message']['templates'][0].keys()
        assert sorted(actual_fields) == sorted(expected_fields)

    @pytest.mark.tier2
    def test_positive_import_json_output_verbose_false(self, module_org):
        """Assert all the required fields displayed in import output when
        verbose is `False`

        :id: 7d7c65f5-1af3-4a9b-ba9e-70130f61d7cb

        :Steps:
            1. Using nailgun or direct API call
               Impot a template with verbose `False` option

        :expectedresults:
            1. Assert json output has all the following fields
               'name', 'imported', 'changed', 'additional_errors', 'exception',
               'validation_errors', 'file'

        :Requirement: Take Templates out of tech preview

        :CaseImportance: Low
        """
        prefix = gen_string('alpha')
        templates = entities.Template().imports(
            data={
                'repo': FOREMAN_TEMPLATE_IMPORT_URL,
                'branch': 'master',
                'filter': 'robottelo',
                'organization_ids': [module_org.id],
                'prefix': prefix,
                'verbose': False,
            }
        )
        expected_fields = [
            'name',
            'imported',
            'changed',
            'additional_errors',
            'exception',
            'validation_errors',
            'file',
            'type',
            'id',
            'additional_info',
        ]
        actual_fields = templates['message']['templates'][0].keys()
        assert sorted(actual_fields) == sorted(expected_fields)

    @pytest.mark.tier2
    def test_positive_import_json_output_changed_key_true(
        self, create_import_export_local_dir, module_org
    ):
        """Assert template imports output `changed` key returns `True` when
        template data gets updated

        :id: 4b866144-822c-4786-9188-53bc7e2dd44a

        :Steps:
            1. Using nailgun or direct API call
               Create a template and import it from a source
            2. Update the template data in source location
            3. Using nailgun or direct API call
               Re-import the same template

        :expectedresults:
            1. On reimport, Assert json output returns 'changed' as `true`
            2. Assert json output returns diff key with difference as value

        :Requirement: Take Templates out of tech preview

        :CaseImportance: Low
        """
        prefix = gen_string('alpha')
        _, dir_path = create_import_export_local_dir
        pre_template = entities.Template().imports(
            data={'repo': dir_path, 'organization_ids': [module_org.id], 'prefix': prefix}
        )
        assert bool(pre_template['message']['templates'][0]['imported'])
        ssh.command(f'echo " Updating Template data." >> {dir_path}/example_template.erb')
        post_template = entities.Template().imports(
            data={'repo': dir_path, 'organization_ids': [module_org.id], 'prefix': prefix}
        )
        assert bool(post_template['message']['templates'][0]['changed'])

    @pytest.mark.tier2
    def test_positive_import_json_output_changed_key_false(
        self, create_import_export_local_dir, module_org
    ):
        """Assert template imports output `changed` key returns `False` when
        template data gets updated

        :id: 64456c0c-c2c6-4a1c-a16e-54ca4a8b66d3

        :Steps:
            1. Using nailgun or direct API call
               Create a template and import it from a source
            2. Dont update the template data in source location
            3. Using nailgun or direct API call
               Re-import the same template

        :expectedresults:
            1. On reiport, Assert json output returns 'changed' as `false`

        :Requirement: Take Templates out of tech preview

        :CaseImportance: Low
        """
        prefix = gen_string('alpha')
        _, dir_path = create_import_export_local_dir
        pre_template = entities.Template().imports(
            data={'repo': dir_path, 'organization_ids': [module_org.id], 'prefix': prefix}
        )
        assert bool(pre_template['message']['templates'][0]['imported'])
        post_template = entities.Template().imports(
            data={'repo': dir_path, 'organization_ids': [module_org.id], 'prefix': prefix}
        )
        assert not bool(post_template['message']['templates'][0]['changed'])

    @pytest.mark.tier2
    def test_positive_import_json_output_name_key(
        self, create_import_export_local_dir, module_org
    ):
        """Assert template imports output `name` key returns correct name

        :id: a5639368-3d23-4a37-974a-889e2ec0916e

        :Steps:
            1. Using nailgun or direct API call
               Create a template with some name and import it from a source

        :expectedresults:
            1. On Import, Assert json output returns 'name' key with correct
            name as per template metadata

        :Requirement: Take Templates out of tech preview

        :CaseImportance: Low
        """
        template_name = gen_string('alpha')
        _, dir_path = create_import_export_local_dir
        ssh.command(f'sed -ie "s/name: .*/name: {template_name}/" {dir_path}/example_template.erb')
        template = entities.Template().imports(
            data={'repo': dir_path, 'organization_ids': [module_org.id]}
        )
        assert 'name' in template['message']['templates'][0].keys()
        assert template_name == template['message']['templates'][0]['name']

    @pytest.mark.tier2
    def test_positive_import_json_output_imported_key(
        self, create_import_export_local_dir, module_org
    ):
        """Assert template imports output `imported` key returns `True` on
        successful import

        :id: 5bc11163-e8f3-4744-8a76-5c16e6e46e86

        :Steps:
            1. Using nailgun or direct API call
               Create a template and import it from a source

        :expectedresults:
            1. On Import, Assert json output returns 'imported' key as `True`

        :Requirement: Take Templates out of tech preview

        :CaseImportance: Low
        """
        prefix = gen_string('alpha')
        _, dir_path = create_import_export_local_dir
        template = entities.Template().imports(
            data={'repo': dir_path, 'organization_ids': [module_org.id], 'prefix': prefix}
        )
        assert bool(template['message']['templates'][0]['imported'])

    @pytest.mark.tier2
    def test_positive_import_json_output_file_key(
        self, create_import_export_local_dir, module_org
    ):
        """Assert template imports output `file` key returns correct file name
        from where the template is imported

        :id: da0b094c-6dc8-4526-b115-8e08bfb05fbb

        :Steps:
            1. Using nailgun or direct API call
               Create a template with some name and import it from a source

        :expectedresults:
            1. Assert json output returns 'file' key with correct
            file name

        :Requirement: Take Templates out of tech preview

        :CaseImportance: Low
        """
        _, dir_path = create_import_export_local_dir
        template = entities.Template().imports(
            data={'repo': dir_path, 'organization_ids': [module_org.id]}
        )
        assert 'example_template.erb' == template['message']['templates'][0]['file']

    @pytest.mark.tier2
    def test_positive_import_json_output_corrupted_metadata(
        self, create_import_export_local_dir, module_org
    ):
        """Assert template imports output returns corrupted metadata error for
        incorrect metadata in template

        :id: 6bd5bc6b-a7a2-4529-9df6-47a670cd86d8

        :Steps:
            1. Create a template with wrong syntax in metadata
            2. Using nailgun or direct API call
               Import above template

        :expectedresults:
            1. Assert json output has error contains
            'Failed to parse metadata' text
            2. Assert 'imported' key returns 'false' value

        :Requirement: Take Templates out of tech preview

        :CaseImportance: Medium
        """
        _, dir_path = create_import_export_local_dir
        ssh.command(f'sed -ie "s/<%#/$#$#@%^$^@@RT$$/" {dir_path}/example_template.erb')
        template = entities.Template().imports(
            data={'repo': dir_path, 'organization_ids': [module_org.id]}
        )
        assert not bool(template['message']['templates'][0]['imported'])
        assert (
            'Failed to parse metadata' == template['message']['templates'][0]['additional_errors']
        )

    @pytest.mark.skip_if_open('BZ:1787355')
    @pytest.mark.tier2
    def test_positive_import_json_output_filtered_skip_message(
        self, create_import_export_local_dir, module_org
    ):
        """Assert template imports output returns template import skipped info
        for templates whose name doesnt match the filter

        :id: db68b5de-7647-4568-b79c-2aec3292328a

        :Steps:
            1. Using nailgun or direct API call
               Create template with name not matching filter

        :expectedresults:
            1. Assert json output has info contains
            'Name is not matching filter condition, skipping' text
            2. Assert 'imported' key returns 'false' value

        :Requirement: Take Templates out of tech preview

        :CaseImportance: Low
        """
        _, dir_path = create_import_export_local_dir
        template = entities.Template().imports(
            data={
                'repo': dir_path,
                'organization_ids': [module_org.id],
                'filter': gen_string('alpha'),
            }
        )
        assert not bool(template['message']['templates'][0]['imported'])
        assert (
            "Skipping, 'name' filtered out based on 'filter' and 'negate' settings"
            == template['message']['templates'][0]['additional_info']
        )

    @pytest.mark.tier2
    def test_positive_import_json_output_no_name_error(
        self, create_import_export_local_dir, module_org
    ):
        """Assert template imports output returns no name error for template
        without name

        :id: 259a8a3a-8749-442d-a2bc-51e9af89ce8c

        :Steps:
            1. Create a template without name in metadata
            2. Using nailgun or direct API call
               Import above template

        :expectedresults:
            1. Assert json output has error contains
            'No 'name' found in metadata' text
            2. Assert 'imported' key returns 'false' value

        :Requirement: Take Templates out of tech preview

        :CaseImportance: Low
        """
        _, dir_path = create_import_export_local_dir
        ssh.command(f'sed -ie "s/name: .*/name: /" {dir_path}/example_template.erb')
        template = entities.Template().imports(
            data={'repo': dir_path, 'organization_ids': [module_org.id]}
        )
        assert not bool(template['message']['templates'][0]['imported'])
        assert (
            "No 'name' found in metadata"
            == template['message']['templates'][0]['additional_errors']
        )

    @pytest.mark.tier2
    def test_positive_import_json_output_no_model_error(
        self, create_import_export_local_dir, module_org
    ):
        """Assert template imports output returns no model error for template
        without model

        :id: d3f1ffe4-58d7-45a8-b278-74e081dc5062

        :Steps:
            1. Create a template without model keyword in metadata
            2. Using nailgun or direct API call
               Import above template

        :expectedresults:
            1. Assert json output has error contains
            'No 'model' found in metadata' text
            2. Assert 'imported' key returns 'false' value

        :Requirement: Take Templates out of tech preview

        :CaseImportance: Low
        """
        _, dir_path = create_import_export_local_dir
        ssh.command(f'sed -ie "/model: .*/d" {dir_path}/example_template.erb')
        template = entities.Template().imports(
            data={'repo': dir_path, 'organization_ids': [module_org.id]}
        )
        assert not bool(template['message']['templates'][0]['imported'])
        assert (
            "No 'model' found in metadata"
            == template['message']['templates'][0]['additional_errors']
        )

    @pytest.mark.tier2
    def test_positive_import_json_output_blank_model_error(
        self, create_import_export_local_dir, module_org
    ):
        """Assert template imports output returns blank model name error for
        template without template name

        :id: 5007b12d-1cf6-49e6-8e54-a189d1a209de

        :Steps:
            1. Create a template with blank model name in metadata
            2. Using nailgun or direct API call
               Import above template

        :expectedresults:
            1. Assert json output has additional_error contains
               'Template type was not found, maybe you are missing a plugin?'
            2. Assert 'imported' key returns 'false' value

        :Requirement: Take Templates out of tech preview

        :CaseImportance: Low
        """
        _, dir_path = create_import_export_local_dir
        ssh.command(f'sed -ie "s/model: .*/model: /" {dir_path}/example_template.erb')
        template = entities.Template().imports(
            data={'repo': dir_path, 'organization_ids': [module_org.id]}
        )
        assert not bool(template['message']['templates'][0]['imported'])
        assert (
            "Template type  was not found, are you missing a plugin?"
            == template['message']['templates'][0]['additional_errors']
        )

    @pytest.mark.tier2
    def test_positive_export_json_output(self, create_import_export_local_dir, module_org):
        """Assert template export output returns template names

        :id: 141b893d-72a3-47c2-bb03-004c757bcfc9

        :Steps:
            1. Using nailgun or direct API call
               Export all the templates

        :expectedresults:
            1. Assert json output has all the exported template names
            and typewise

        :Requirement: Take Templates out of tech preview

        :CaseImportance: Low
        """
        prefix = gen_string('alpha')
        imported_templates = entities.Template().imports(
            data={
                'repo': FOREMAN_TEMPLATE_IMPORT_URL,
                'branch': 'automation',
                'organization_ids': [module_org.id],
                'prefix': prefix,
                'dirname': 'import',
            }
        )
        imported_count = [
            template['imported'] for template in imported_templates['message']['templates']
        ].count(True)
        assert imported_count == 18  # Total Count
        # Export some filtered templates to local dir
        _, dir_path = create_import_export_local_dir
        exported_templates = entities.Template().exports(
            data={'repo': dir_path, 'organization_ids': [module_org.id], 'filter': prefix}
        )
        exported_count = [
            template['exported'] for template in exported_templates['message']['templates']
        ].count(True)
        assert exported_count == 18
        assert 'name' in exported_templates['message']['templates'][0].keys()
        assert (
            ssh.command(
                f'[ -d {dir_path}/job_templates ] && '
                f'[ -d {dir_path}/partition_tables_templates ] && '
                f'[ -d {dir_path}/provisioning_templates ] && '
                f'[ -d {dir_path}/report_templates ]'
            ).return_code
            == 0
        )

    @pytest.mark.tier3
    def test_positive_import_log_to_production(self, module_org):
        """Assert template import logs are logged to production logs

        :id: 19ed0e6a-ee77-4e28-86c9-49db1adec479

        :Steps:
            1. Using nailgun or direct API call
               Import template from a source

        :expectedresults:
            1. Assert template import task and status logged to production log

        :Requirement: Take Templates out of tech preview

        :CaseLevel: System

        :CaseImportance: Low
        """
        entities.Template().imports(
            data={
                'repo': FOREMAN_TEMPLATE_IMPORT_URL,
                'branch': 'master',
                'organization_ids': [module_org.id],
                'filter': 'empty',
            }
        )
        time.sleep(5)
        result = ssh.command(
            'grep -i \'Started POST "/api/v2/templates/import"\' /var/log/foreman/production.log'
        )
        assert result.return_code == 0

    @pytest.mark.tier3
    def test_positive_export_log_to_production(self, create_import_export_local_dir, module_org):
        """Assert template export logs are logged to production logs

        :id: 8ae370b1-84e8-436e-a7d7-99cd0b8f45b1

        :Steps:
            1. Using nailgun or direct API call
               Export template to destination

        :expectedresults:
            1. Assert template export task and status logged to production log

        :Requirement: Take Templates out of tech preview

        :CaseLevel: System

        :CaseImportance: Low
        """
        entities.Template().imports(
            data={
                'repo': FOREMAN_TEMPLATE_IMPORT_URL,
                'branch': 'master',
                'organization_ids': [module_org.id],
                'filter': 'empty',
            }
        )
        _, dir_path = create_import_export_local_dir
        entities.Template().exports(
            data={'repo': dir_path, 'organization_ids': [module_org.id], 'filter': 'empty'}
        )
        time.sleep(5)
        result = ssh.command(
            'grep -i \'Started POST "/api/v2/templates/export"\' /var/log/foreman/production.log'
        )
        assert result.return_code == 0
