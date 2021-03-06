
from south.db import db
from django.db import models
from art_server.incus.models import *

class Migration:
    
    def forwards(self, orm):
        
        # Adding model 'ABDevice'
        db.create_table('incus_abdevice', (
            ('id', models.AutoField(primary_key=True)),
            ('name', models.CharField(max_length=1024, null=False, blank=False)),
            ('ip', models.IPAddressField(null=False, blank=False)),
            ('port', models.IntegerField(default=55128, null=False, blank=False)),
        ))
        db.send_create_signal('incus', ['ABDevice'])
        
        # Adding model 'ABChannelGroup'
        db.create_table('incus_abchannelgroup', (
            ('id', models.AutoField(primary_key=True)),
            ('name', models.CharField(max_length=1024, null=False, blank=False)),
        ))
        db.send_create_signal('incus', ['ABChannelGroup'])
        
        # Adding model 'ABChannel'
        db.create_table('incus_abchannel', (
            ('id', models.AutoField(primary_key=True)),
            ('audioBoxDevice', models.ForeignKey(orm.ABDevice, null=False, blank=False)),
            ('number', models.IntegerField(null=False, blank=False)),
            ('channel_group', models.ForeignKey(orm.ABChannelGroup, null=True, blank=True)),
            ('gain', models.FloatField(default=0, null=False)),
        ))
        db.send_create_signal('incus', ['ABChannel'])
        
    
    
    def backwards(self, orm):
        
        # Deleting model 'ABDevice'
        db.delete_table('incus_abdevice')
        
        # Deleting model 'ABChannelGroup'
        db.delete_table('incus_abchannelgroup')
        
        # Deleting model 'ABChannel'
        db.delete_table('incus_abchannel')
        
    
    
    models = {
        'incus.abdevice': {
            'id': ('models.AutoField', [], {'primary_key': 'True'}),
            'ip': ('models.IPAddressField', [], {'null': 'False', 'blank': 'False'}),
            'name': ('models.CharField', [], {'max_length': '1024', 'null': 'False', 'blank': 'False'}),
            'port': ('models.IntegerField', [], {'default': '55128', 'null': 'False', 'blank': 'False'})
        },
        'incus.abchannelgroup': {
            'id': ('models.AutoField', [], {'primary_key': 'True'}),
            'name': ('models.CharField', [], {'max_length': '1024', 'null': 'False', 'blank': 'False'})
        },
        'incus.abchannel': {
            'audioBoxDevice': ('models.ForeignKey', ["orm['incus.ABDevice']"], {'null': 'False', 'blank': 'False'}),
            'channel_group': ('models.ForeignKey', ["orm['incus.ABChannelGroup']"], {'null': 'True', 'blank': 'True'}),
            'gain': ('models.FloatField', [], {'default': '0', 'null': 'False'}),
            'id': ('models.AutoField', [], {'primary_key': 'True'}),
            'number': ('models.IntegerField', [], {'null': 'False', 'blank': 'False'})
        }
    }
    
    complete_apps = ['incus']
