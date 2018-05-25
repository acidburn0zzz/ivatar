from django.test import TestCase
from django.test import Client
from django.urls import reverse

from libravatar import libravatar_url
from urllib.parse import urlsplit

import io
import os
import django
os.environ['DJANGO_SETTINGS_MODULE'] = 'ivatar.settings'
django.setup()

from ivatar import settings  # noqa
from ivatar.ivataraccount.forms import MAX_NUM_UNCONFIRMED_EMAILS_DEFAULT  # noqa

from django.contrib.auth.models import User  # noqa
from django.contrib.auth import authenticate  # noqa
from ivatar.utils import random_string  # noqa
from ivatar.ivataraccount.models import Photo, ConfirmedOpenId  # noqa


class Tester(TestCase):
    client = Client()
    user = None
    username = random_string()
    password = random_string()
    email = '%s@%s.%s' % (username, random_string(), random_string(2))
    # Dunno why random tld doens't work, but I'm too lazy now to investigate
    openid = 'http://%s.%s.%s' % (username, random_string(), 'org')

    def login(self):
        '''
        Login as user
        '''
        self.client.login(username=self.username, password=self.password)

    def setUp(self):
        '''
        Prepare for tests.
        - Create user
        '''
        self.user = User.objects.create_user(
            username=self.username,
            password=self.password,
        )

    def test_new_user(self):
        """
        Create a new user
        """
        response = self.client.get(reverse('new_account'))
        self.assertEqual(response.status_code, 200, 'no 200 ok?')
        # Empty database / eliminate existing users
        User.objects.all().delete()
        url = reverse('new_account')
        response = self.client.post(
            url, {
                'username': self.username,
                'password1': self.password,
                'password2': self.password,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200, 'unable to create user?')
        self.assertEqual(response.context[0]['user'].username, self.username)

    def test_new_user_twice(self):
        """
        Try to create a user that already exists
        """
        response = self.client.get(reverse('new_account'))
        self.assertEqual(response.status_code, 200, 'no 200 ok?')
        # Due to setUp(), we already have this user!
        url = reverse('new_account')
        response = self.client.post(
            url, {
                'username': self.username,
                'password1': self.password,
                'password2': self.password,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200, 'unable to create user?')
        self.assertEqual(response.context[0]['user'].username, '')
        self.assertContains(
            response,
            'A user with that username already exists.', 1, 200,
            'can we create a user a second time???')

    def test_set_password(self):
        """
        Change the user password
        """
        self.login()
        response = self.client.get(reverse('password_set'))
        self.assertEqual(response.status_code, 200, 'no 200 ok?')
        self.password = random_string()
        response = self.client.post(
            reverse('password_set'), {
                'new_password1': self.password,
                'new_password2': self.password,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200, 'cannot change password?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'password changed successfully - please login again',
            'password change not successful?')

        self.assertIsNotNone(authenticate(
            username=self.username,
            password=self.password,
        ), 'cannot authenticate with new password!?')

        self.login()
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.context[0]['user'].is_anonymous, False)

    def test_add_email(self):
        """
        Add e-mail address
        """
        self.login()
        response = self.client.get(reverse('add_email'))
        self.assertEqual(response.status_code, 200, 'no 200 ok?')
        # Avoid sending out mails
        settings.EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
        response = self.client.post(
            reverse('add_email'), {
                'email': self.email,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200, 'cannot add email?')
        self.assertEqual(
            len(response.context[0]['messages']), 1,
            'there must not be more or less than ONE (1) message')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Address added successfully', 'unable to add mail address?')

    def test_confirm_email(self):
        '''
        Confirm unconfirmed email
        '''
        self.login()
        # Avoid sending out mails
        settings.EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
        response = self.client.post(
            reverse('add_email'), {
                'email': self.email,
            },
            follow=True,
        )
        unconfirmed = self.user.unconfirmedemail_set.first()
        verification_key = unconfirmed.verification_key
        url = reverse('confirm_email', args=[verification_key])
        response = self.client.get(url)
        self.assertEqual(
            response.status_code, 200,
            'unable to confirm mail address?')

        self.assertEqual(
            self.user.unconfirmedemail_set.count(), 0,
            'there must not be any unconfirmed address, after confirming it')
        self.assertEqual(
            self.user.confirmedemail_set.count(), 1,
            'there must not be more or less than ONE (1) confirmed address!')

    def test_confirm_email_w_invalid_auth_key(self):
        '''
        Test confirmation with invalid auth key
        '''
        self.login()
        # Avoid sending out mails
        settings.EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
        response = self.client.post(
            reverse('add_email'), {
                'email': self.email,
            },
            follow=True,
        )
        url = reverse('confirm_email', args=['x'])
        response = self.client.get(url, follow=True)
        self.assertEqual(
            response.status_code, 200,
            'Not able to request confirmation - without verification key?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Verification key incorrect',
            'Confirm w/o verification key does not produce error message?')

    def test_confirm_email_w_inexisting_auth_key(self):
        '''
        Test confirmation with inexisting auth key
        '''
        self.login()
        # Avoid sending out mails
        settings.EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
        response = self.client.post(
            reverse('add_email'), {
                'email': self.email,
            },
            follow=True,
        )
        url = reverse('confirm_email', args=['x'*64])
        response = self.client.get(url, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            'Not able to request confirmation - without verification key?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Verification key does not exist',
            'Confirm w/o inexisting key does not produce error message?')

    def test_remove_confirmed_email(self):
        '''
        Remove confirmed email
        '''
        self.login()
        # Avoid sending out mails
        settings.EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
        response = self.client.post(
            reverse('add_email'), {
                'email': self.email,
            },
        )  # Create test address
        unconfirmed = self.user.unconfirmedemail_set.first()
        verification_key = unconfirmed.verification_key
        url = reverse('confirm_email', args=[verification_key])
        self.client.get(url)  # Confirm
        url = reverse(
            'remove_confirmed_email',
            args=[self.user.confirmedemail_set.first().id])
        response = self.client.post(url, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            'unable to remove confirmed address?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Address removed',
            'Removing confirmed mail does not work?')

    def test_remove_not_existing_confirmed_email(self):
        '''
        Try removing confirmed mail that doesn't exist
        '''
        self.login()
        url = reverse('remove_confirmed_email', args=[1234])
        response = self.client.post(url, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            'removing email does not redirect to profile?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Address does not exist',
            'Removing not existing (confirmed) address, should produce an\
                error message!')

    def test_remove_unconfirmed_email(self):
        '''
        Remove unconfirmed email
        '''
        self.login()
        # Avoid sending out mails
        settings.EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
        response = self.client.post(
            reverse('add_email'), {
                'email': self.email,
            },
        )  # Create test address
        url = reverse(
            'remove_unconfirmed_email',
            args=[self.user.unconfirmedemail_set.first().id])
        response = self.client.post(url, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            'unable to remove unconfirmed address?')
        # Take care, since we do not fetch any page now, the message we need
        # to check is the _second_ (aka [1], since first is [0])
        self.assertEqual(
            str(list(response.context[0]['messages'])[1]),
            'Address removed',
            'Removing unconfirmed mail does not work?')

    def test_gravatar_photo_import(self):
        '''
        import photo from Gravatar (with known mail address)
        '''
        self.login()
        # Avoid sending out mails
        settings.EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
        response = self.client.post(
            reverse('add_email'), {
                'email': 'oliver@linux-kernel.at',  # Whohu, static :-[
            },
        )  # Create test address
        unconfirmed = self.user.unconfirmedemail_set.first()
        verification_key = unconfirmed.verification_key
        url = reverse('confirm_email', args=[verification_key])
        self.client.get(url)  # Confirm

        url = reverse(
            'import_photo',
            args=[self.user.confirmedemail_set.first().id])
        response = self.client.post(url, {
                'photo_Gravatar': 1,
            },
            follow=True
        )
        self.assertEqual(
            response.status_code,
            200,
            'unable to import photo from Gravatar?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Image successfully imported',
            'Importing gravatar photo did not work?')
        self.assertIsInstance(
            self.user.photo_set.first(),
            Photo,
            'why is there no Photo (instance)?')

    def test_raw_image(self):
        '''
        test raw image view (as seen in profile <img src=
        '''

        # Ensure we have a photo
        self.test_gravatar_photo_import()
        response = self.client.get(
            reverse('raw_image', args=[self.user.photo_set.first().id]))
        self.assertEqual(response.status_code, 200, 'cannot fetch photo?')
        # Probably not the best way to access the content type
        self.assertEqual(
            response._headers['content-type'][1],
            'image/jpg',
            'Content type wrong!?')

        self.assertEqual(
            response.content,
            self.user.photo_set.first().data,
            'raw_image should return the same content as if we\
            read it directly from the DB')

    def test_delete_photo(self):
        '''
        test deleting the photo
        '''

        # Ensure we have a photo
        self.test_gravatar_photo_import()

        url = reverse('delete_photo', args=[self.user.photo_set.first().id])
        response = self.client.get(url, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            'deleting photo doesnt work?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Photo deleted successfully',
            'Photo deletion did not work?')

    def test_delete_inexisting_photo(self):
        '''
        test deleting the photo
        '''

        # Ensure we have a photo
        self.test_gravatar_photo_import()

        url = reverse('delete_photo', args=[1234])
        response = self.client.get(url, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            'post to delete does not work?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'No such image or no permission to delete it',
            'Deleting photo that does not exist, should return error message')

    def test_too_many_unconfirmed_email(self):
        '''
        Request too many unconfirmed email addresses, make sure we
        cannot add more
        '''
        self.login()
        # Avoid sending out mails
        settings.EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'

        max_num_unconfirmed = getattr(
            settings,
            'MAX_NUM_UNCONFIRMED_EMAILS',
            MAX_NUM_UNCONFIRMED_EMAILS_DEFAULT)

        for i in range(max_num_unconfirmed+1):
            response = self.client.post(
                reverse('add_email'), {
                    'email': '%i.%s' % (i, self.email),
                },
            )  # Create test addresses + 1 too much
        response = self.client.get(reverse('profile'))
        self.assertEqual(
            response.status_code,
            200,
            'why does profile page not work!?')
        # Take care, since we do did not fetch any pages after adding mail
        # addresses, the messages still sit there waiting to be fetched!!
        # Therefore the message index we need to use is max_num_unconfirmed!
        self.assertEqual(
            str(list(response.context[0]['messages'])[max_num_unconfirmed]),
            'Address not added',
            'Too many unconfirmed address, should return a\
            "not added" messsage!')

    def test_add_mail_address_twice(self):
        '''
        Request the same mail address two times, should not lead to
        having the same address twice
        '''
        self.login()
        # Avoid sending out mails
        settings.EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'

        for _ in range(2):
            response = self.client.post(
                reverse('add_email'), {
                    'email': self.email,
                },
            )  # Request adding test address twice
        response = self.client.get(reverse('profile'))
        self.assertEqual(
            response.status_code,
            200,
            'why does profile page not work!?')
        # Take care, since we do did not fetch any pages after adding mail
        # addresses, the messages still sit there waiting to be fetched!!
        self.assertEqual(
            str(list(response.context[0]['messages'])[1]),
            'Address not added',
            'Adding address twice must lead to "Address not added" message!')

    def test_add_already_confirmed_email(self):
        '''
        Request adding mail address that is already confirmed (by someone)
        '''
        # Create test mail and confirm it, reuse test code
        # Should set EMAIL_BACKEND, so no need to do it here
        self.test_confirm_email()

        response = self.client.post(
            reverse('add_email'), {
                'email': self.email,
            },
        )  # Request adding test address a second time
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200, 'why does profile page not\
                work!?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Address not added', 'Adding already added address must lead to\
            "Address not added" message!')

    def test_remove_unconfirmed_non_existing_email(self):
        '''
        Remove unconfirmed email that doesn't exist
        '''
        self.login()
        url = reverse('remove_unconfirmed_email', args=[1234])
        response = self.client.post(url, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            'unable to remove non existing address?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Address does not exist', 'Removing address that does not\
            exist, should return error message!')

    def test_upload_image(self, test_only_one=True):
        '''
        Test uploading image
        '''
        self.login()
        url = reverse('upload_photo')
        # rb => Read binary
        with open(os.path.join(
                settings.STATIC_ROOT, 'img', 'deadbeef.png'), 'rb') as photo:
            response = self.client.post(url, {
                'photo': photo,
                'not_porn': True,
                'can_distribute': True,
            }, follow=True)
        if test_only_one:
            self.assertEqual(
                self.user.photo_set.count(), 1,
                'there must be exactly one photo now!')
            self.assertEqual(
                str(list(response.context[0]['messages'])[-1]),
                'Successfully uploaded',
                'A valid image should return a success message!')
            self.assertEqual(
                self.user.photo_set.first().format, 'png',
                'Format must be png, since we uploaded a png!')
        else:
            return response

    def test_upload_too_many_images(self):
        '''
        Test uploading more images than we are allowed
        '''
        for _ in range(settings.MAX_NUM_PHOTOS+1):
            response = self.test_upload_image(test_only_one=False)
        self.assertEqual(
            self.user.photo_set.count(),
            settings.MAX_NUM_PHOTOS,
            'there may not be more photos than allowed!')
        # Take care we need to check the last message
        self.assertEqual(
            str(list(response.context[0]['messages'])[-1]),
            'Maximum number of photos (%i) reached' % settings.MAX_NUM_PHOTOS,
            'Adding more than allowed images, should return error message!')

    def test_upload_too_big_image(self):
        '''
        Test uploading image that is too big
        '''
        self.login()
        url = reverse('upload_photo')
        # rb => Read binary
        response = self.client.post(url, {
            'photo': io.StringIO('x'*(settings.MAX_PHOTO_SIZE+1)),
            'not_porn': True,
            'can_distribute': True,
        }, follow=True)
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Image too big',
            'Uploading too big image, should return error message!')

    def test_upload_invalid_image(self):
        '''
        Test invalid image data
        '''
        self.login()
        url = reverse('upload_photo')
        # rb => Read binary
        response = self.client.post(url, {
            'photo': io.StringIO('x'),
            'not_porn': True,
            'can_distribute': True,
        }, follow=True)
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Invalid Format',
            'Invalid img data should return error message!')

    def test_upload_invalid_image_format(self):
        '''
        Test if invalid format is correctly detected
        '''
        self.login()
        url = reverse('upload_photo')
        # rb => Read binary
        with open(os.path.join(
                settings.STATIC_ROOT, 'img', 'mm.svg'), 'rb') as photo:
            response = self.client.post(url, {
                'photo': photo,
                'not_porn': True,
                'can_distribute': True,
            }, follow=True)
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Invalid Format',
            'Invalid img data should return error message!')

    def test_upload_gif_image(self):
        '''
        Test if gif is correctly detected
        '''
        self.login()
        url = reverse('upload_photo')
        # rb => Read binary
        with open(os.path.join(
                settings.STATIC_ROOT,
                'img',
                'broken.gif'), 'rb') as photo:
            response = self.client.post(url, {
                'photo': photo,
                'not_porn': True,
                'can_distribute': True,
            }, follow=True)
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Successfully uploaded',
            'Invalid image data should return error message!')
        self.assertEqual(
            self.user.photo_set.first().format, 'gif',
            'Format must be gif, since we uploaded a GIF!')

    def test_upload_unsupported_tif_image(self):
        '''
        Test if unsupported format is correctly detected
        '''
        self.login()
        url = reverse('upload_photo')
        # rb => Read binary
        with open(os.path.join(
                settings.STATIC_ROOT,
                'img',
                'hackergotchi_test.tif'), 'rb') as photo:
            response = self.client.post(url, {
                'photo': photo,
                'not_porn': True,
                'can_distribute': True,
            }, follow=True)
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Invalid Format',
            'Invalid img data should return error message!')

    def test_automatic_photo_assign_to_confirmed_mail(self):
        self.test_upload_image()
        self.test_confirm_email()
        confirmed = self.user.confirmedemail_set.first()
        self.assertEqual(confirmed.photo, self.user.photo_set.first())

    def test_assign_photo_to_email(self):
        self.test_confirm_email()
        self.test_upload_image()
        self.assertIsNone(self.user.confirmedemail_set.first().photo)
        url = reverse(
            'assign_photo_email',
            args=[self.user.confirmedemail_set.first().id])
        # The get is for the view - test context data
        self.client.get(url, {
            'photo_id': self.user.photo_set.first().id,
        })
        # The post is for the actual assigning
        response = self.client.post(url, {
            'photo_id': self.user.photo_set.first().id,
        }, follow=True)
        self.assertEqual(response.status_code, 200, 'cannot assign photo?')
        self.assertEqual(
            self.user.confirmedemail_set.first().photo,
            self.user.photo_set.first())

    def test_assign_invalid_photo_id_to_email(self):
        self.test_confirm_email()
        self.test_upload_image()
        self.assertIsNone(self.user.confirmedemail_set.first().photo)
        url = reverse(
            'assign_photo_email',
            args=[self.user.confirmedemail_set.first().id])
        response = self.client.post(url, {
            'photo_id': 1234,
        }, follow=True)
        self.assertEqual(
            response.status_code, 200,
            'cannot post assign photo request?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Photo does not exist',
            'Assign non existing photo, does not return error message?')

    def test_post_to_assign_photo_without_photo_id(self):
        self.test_confirm_email()
        self.test_upload_image()
        self.assertIsNone(self.user.confirmedemail_set.first().photo)
        url = reverse(
            'assign_photo_email',
            args=[self.user.confirmedemail_set.first().id])
        response = self.client.post(url, {}, follow=True)
        self.assertEqual(
            response.status_code, 200,
            'cannot post assign photo request?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Invalid request [photo_id] missing',
            'Assign non existing photo, does not return error message?')

    def test_assign_photo_to_inexisting_mail(self):
        self.test_upload_image()
        url = reverse('assign_photo_email', args=[1234])
        response = self.client.post(url, {
            'photo_id': self.user.photo_set.first().id,
        }, follow=True)
        self.assertEqual(
            response.status_code, 200,
            'cannot post assign photo request?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Invalid request',
            'Assign non existing photo, does not return error message?')

    def test_import_photo_with_inexisting_email(self):
        self.login()
        url = reverse('import_photo', args=[1234])
        response = self.client.post(url, {}, follow=True)
        self.assertEqual(
            response.status_code, 200,
            'cannot post import photo request?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Address does not exist',
            'Import photo with inexisting mail id,\
            does not return error message?')

    def test_import_nothing(self):
        self.test_confirm_email()
        url = reverse(
            'import_photo',
            args=[self.user.confirmedemail_set.first().id])
        response = self.client.post(url, {}, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            'cannot post import photo request?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Nothing importable',
            'Importing with email that does not exist in Gravatar,\
            should return an error message!')

    def test_add_openid(self, confirm=True):
        '''
        Test if adding an OpenID works
        '''
        self.login()
        # Get page
        response = self.client.get(reverse('add_openid'))
        self.assertEqual(
            response.status_code,
            200,
            'Fetching page to add OpenID fails?')

        response = self.client.post(
            reverse('add_openid'), {
                 # Whohu, static... :-[
                'openid': self.openid,
            },
        )
        self.assertEqual(response.status_code, 302, 'OpenID must redirect')

        if confirm:
            # Manual confirm, since testing is _really_ hard!
            unconfirmed = self.user.unconfirmedopenid_set.first()
            confirmed = ConfirmedOpenId()
            confirmed.user = unconfirmed.user
            confirmed.ip_address = '127.0.0.1'
            confirmed.openid = unconfirmed.openid
            confirmed.save()
            unconfirmed.delete()

    def test_add_openid_twice(self):
        '''
        Test if adding OpenID a second time works - it shouldn't
        '''
        self.login()
        # Get page
        response = self.client.get(reverse('add_openid'))
        self.assertEqual(
            response.status_code,
            200,
            'Fetching page to add OpenID fails?')

        response = self.client.post(
            reverse('add_openid'), {
                 # Whohu, static... :-[
                'openid': self.openid,
            },
        )
        self.assertEqual(response.status_code, 302, 'OpenID must redirect')

        response = self.client.post(
            reverse('add_openid'), {
                 # Whohu, static... :-[
                'openid': self.openid,
            },
        )
        self.assertEqual(response.status_code, 302, 'OpenID must redirect')
        self.assertEqual(
            self.user.unconfirmedopenid_set.count(),
            1, 'There must only be one unconfirmed ID!')

        # Manual confirm, since testing is _really_ hard!
        unconfirmed = self.user.unconfirmedopenid_set.first()
        confirmed = ConfirmedOpenId()
        confirmed.user = unconfirmed.user
        confirmed.ip_address = '127.0.0.1'
        confirmed.openid = unconfirmed.openid
        confirmed.save()
        unconfirmed.delete()

        # Try adding it again - although already confirmed
        response = self.client.post(
            reverse('add_openid'), {
                 # Whohu, static... :-[
                'openid': self.openid,
            },
        )
        self.assertEqual(response.status_code, 302, 'OpenID must redirect')
        self.assertEqual(
            self.user.unconfirmedopenid_set.count(),
            0, 'There must be no unconfirmed ID, since we tried adding an\
                already confirmed ID!')

    def test_assign_photo_to_openid(self):
        self.test_add_openid()
        self.test_upload_image()
        self.assertIsNone(self.user.confirmedopenid_set.first().photo)
        url = reverse(
            'assign_photo_openid',
            args=[self.user.confirmedopenid_set.first().id])
        # The get is for the view - test context data
        self.client.get(url, {
            'photo_id': self.user.photo_set.first().id,
        })
        # The post is for the actual assigning
        response = self.client.post(url, {
            'photo_id': self.user.photo_set.first().id,
        }, follow=True)
        self.assertEqual(response.status_code, 200, 'cannot assign photo?')
        self.assertEqual(
            self.user.confirmedopenid_set.first().photo,
            self.user.photo_set.first())

    def test_assign_invalid_photo_id_to_openid(self):
        self.test_add_openid()
        self.assertIsNone(self.user.confirmedopenid_set.first().photo)
        url = reverse(
            'assign_photo_openid',
            args=[self.user.confirmedopenid_set.first().id])
        response = self.client.post(url, {
            'photo_id': 1234,
        }, follow=True)
        self.assertEqual(
            response.status_code, 200,
            'cannot post assign photo request?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[-1]),
            'Photo does not exist',
            'Assign non existing photo, does not return error message?')

    def test_post_to_assign_photo_openid_without_photo_id(self):
        self.test_add_openid()
        self.test_upload_image()
        self.assertIsNone(self.user.confirmedopenid_set.first().photo)
        url = reverse(
            'assign_photo_openid',
            args=[self.user.confirmedopenid_set.first().id])
        response = self.client.post(url, {}, follow=True)
        self.assertEqual(
            response.status_code, 200,
            'cannot post assign photo request?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Invalid request [photo_id] missing',
            'Assign non existing photo, does not return error message?')

    def test_assign_photo_to_openid_inexisting_openid(self):
        self.test_upload_image()
        url = reverse('assign_photo_openid', args=[1234])
        response = self.client.post(url, {
            'photo_id': self.user.photo_set.first().id,
        }, follow=True)
        self.assertEqual(
            response.status_code, 200,
            'cannot post assign photo request?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'Invalid request',
            'Assign non existing photo, does not return error message?')

    def test_remove_confirmed_openid(self):
        '''
        Remove confirmed openid
        '''
        self.test_add_openid()
        url = reverse(
            'remove_confirmed_openid',
            args=[self.user.confirmedopenid_set.first().id])
        response = self.client.post(url, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            'unable to remove confirmed openid?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[-1]),
            'ID removed',
            'Removing confirmed openid does not work?')

    def test_remove_not_existing_confirmed_openid(self):
        '''
        Try removing confirmed openid that doesn't exist
        '''
        self.login()
        url = reverse('remove_confirmed_openid', args=[1234])
        response = self.client.post(url, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            'removing id does not redirect to profile?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'ID does not exist',
            'Removing not existing (confirmed) address, should produce an\
                error message!')

    def test_remove_unconfirmed_openid(self):
        '''
        Remove unconfirmed openid
        '''
        self.test_add_openid(confirm=False)
        url = reverse(
            'remove_unconfirmed_openid',
            args=[self.user.unconfirmedopenid_set.first().id])
        response = self.client.post(url, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            'unable to remove unconfirmed address?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[-1]),
            'ID removed',
            'Removing unconfirmed mail does not work?')

    def test_remove_unconfirmed_inexisting_openid(self):
        '''
        Remove unconfirmed openid that doesn't exist
        '''
        self.login()
        url = reverse(
            'remove_unconfirmed_openid',
            args=[1234])
        response = self.client.post(url, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            'unable to remove unconfirmed address?')
        self.assertEqual(
            str(list(response.context[0]['messages'])[0]),
            'ID does not exist',
            'Removing an inexisting openid should return an error message')

    def test_openid_redirect_view(self):
        '''
        Test redirect view
        '''
        self.test_add_openid(confirm=False)
        url = reverse(
            'openid_redirection',
            args=[self.user.unconfirmedopenid_set.first().id])
        response = self.client.get(url, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            'unable to remove unconfirmed address?')
        self.assertContains(
            response,
            'OpenID discovery failed: ', 1, 200,
            'This request must return an error in test mode'
        )

    def test_set_photo_on_openid(self):
        '''
        Test the set_photo function on our ConfirmedOpenId model.
        '''
        self.test_add_openid()
        self.test_upload_image()
        self.assertIsNone(self.user.confirmedopenid_set.first().photo)
        self.user.confirmedopenid_set.first().set_photo(
            self.user.photo_set.first()
        )
        self.assertEqual(
            self.user.confirmedopenid_set.first().photo,
            self.user.photo_set.first(),
            'set_photo did not work!?')

    def test_avatar_url_mail(self):
        '''
        Test fetching avatar via mail
        '''
        self.test_upload_image()
        self.test_confirm_email()
        urlobj = urlsplit(libravatar_url(
            email=self.user.confirmedemail_set.first().email)
        )
        url = urlobj.path
        response = self.client.get(url, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            'unable to fetch avatar?')
        self.assertEqual(
            response.content,
            self.user.photo_set.first().data,
            'Why is this not the same data?')

    def test_avatar_url_openid(self):
        '''
        Test fetching avatar via openid
        '''
        self.test_assign_photo_to_openid()
        urlobj = urlsplit(libravatar_url(
            openid=self.user.confirmedopenid_set.first().openid)
        )
        url = urlobj.path
        response = self.client.get(url, follow=True)
        self.assertEqual(
            response.status_code,
            200,
            'unable to fetch avatar?')
        self.assertEqual(
            response.content,
            self.user.photo_set.first().data,
            'Why is this not the same data?')

    def test_avatar_url_inexisting_mail_digest(self):
        '''
        Test fetching avatar via inexisting mail digest
        '''
        self.test_upload_image()
        self.test_confirm_email()
        urlobj = urlsplit(libravatar_url(
            email=self.user.confirmedemail_set.first().email)
        )
        # Simply delete it, then it digest is 'correct', but
        # the hash is no longer there
        self.user.confirmedemail_set.first().delete()
        url = urlobj.path
        self.assertRaises(Exception, lambda:
                          self.client.get(url, follow=True))
