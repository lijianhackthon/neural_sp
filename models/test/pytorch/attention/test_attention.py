#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Test attention-besed models (pytorch)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import sys
import time
import unittest

import torch
import torch.nn as nn
torch.manual_seed(1623)
torch.cuda.manual_seed_all(1623)

sys.path.append('../../../../')
from models.pytorch.attention.attention_seq2seq import AttentionSeq2seq
from models.test.data import generate_data, idx2char, idx2word
from utils.measure_time_func import measure_time
from utils.evaluation.edit_distance import compute_cer, compute_wer
from utils.training.learning_rate_controller import Controller


class TestAttention(unittest.TestCase):

    def test(self):
        print("Attention Working check.")

        # Label smoothing
        self.check(encoder_type='lstm', bidirectional=True,
                   decoder_type='lstm', label_smoothing=True)

        # Joint CTC-Attention
        self.check(encoder_type='lstm', bidirectional=True,
                   decoder_type='lstm', ctc_loss_weight=0.2)

        # CNN encoder
        self.check(encoder_type='cnn', decoder_type='lstm', batch_norm=True)

        # Initialize decoder state
        self.check(encoder_type='lstm', bidirectional=True,
                   decoder_type='lstm', init_dec_state='zero')
        self.check(encoder_type='lstm', bidirectional=True,
                   decoder_type='lstm', init_dec_state='mean')
        self.check(encoder_type='lstm', bidirectional=True,
                   decoder_type='lstm', init_dec_state='final')

        # Pyramidal encoder
        self.check(encoder_type='lstm', bidirectional=True,
                   decoder_type='lstm', subsample='drop')
        self.check(encoder_type='lstm', bidirectional=True,
                   decoder_type='lstm', subsample='concat')

        # Projection layer
        self.check(encoder_type='lstm', bidirectional=False, projection=True,
                   decoder_type='lstm')

        # Residual LSTM encoder
        self.check(encoder_type='lstm', bidirectional=True,
                   decoder_type='lstm', residual=True)
        self.check(encoder_type='lstm', bidirectional=True,
                   decoder_type='lstm', dense_residual=True)

        # CLDNN encoder
        self.check(encoder_type='lstm', bidirectional=True,
                   decoder_type='lstm', conv=True)
        self.check(encoder_type='lstm', bidirectional=True,
                   decoder_type='lstm', conv=True, batch_norm=True)

        # word-level attention
        self.check(encoder_type='lstm', bidirectional=True,
                   decoder_type='lstm', attention_type='dot_product',
                   label_type='word')

        # unidirectional & bidirectional
        self.check(encoder_type='lstm', bidirectional=True,
                   decoder_type='lstm')
        self.check(encoder_type='lstm', bidirectional=False,
                   decoder_type='lstm')
        self.check(encoder_type='gru', bidirectional=True,
                   decoder_type='gru')
        self.check(encoder_type='gru', bidirectional=False,
                   decoder_type='gru')

        # Attention type
        self.check(encoder_type='lstm', bidirectional=True,
                   decoder_type='lstm', attention_type='content')
        self.check(encoder_type='lstm', bidirectional=True,
                   decoder_type='lstm', attention_type='location')
        self.check(encoder_type='lstm', bidirectional=True,
                   decoder_type='lstm', attention_type='dot_product')

    @measure_time
    def check(self, encoder_type, decoder_type, bidirectional=False,
              attention_type='location', label_type='char',
              subsample=False, projection=False, init_dec_state='final',
              ctc_loss_weight=0, conv=False, batch_norm=False,
              residual=False, dense_residual=False, label_smoothing=False):

        print('==================================================')
        print('  label_type: %s' % label_type)
        print('  encoder_type: %s' % encoder_type)
        print('  bidirectional: %s' % str(bidirectional))
        print('  projection: %s' % str(projection))
        print('  decoder_type: %s' % decoder_type)
        print('  init_dec_state: %s' % init_dec_state)
        print('  attention_type: %s' % attention_type)
        print('  subsample: %s' % str(subsample))
        print('  ctc_loss_weight: %s' % str(ctc_loss_weight))
        print('  conv: %s' % str(conv))
        print('  batch_norm: %s' % str(batch_norm))
        print('  residual: %s' % str(residual))
        print('  dense_residual: %s' % str(dense_residual))
        print('  label_smoothing: %s' % str(label_smoothing))
        print('==================================================')

        if conv or encoder_type == 'cnn':
            # pattern 1
            # conv_channels = [32, 32]
            # conv_kernel_sizes = [[41, 11], [21, 11]]
            # conv_strides = [[2, 2], [2, 1]]
            # poolings = [[], []]

            # pattern 2 (VGG like)
            conv_channels = [64, 64]
            conv_kernel_sizes = [[3, 3], [3, 3]]
            conv_strides = [[1, 1], [1, 1]]
            poolings = [[2, 2], [2, 2]]
        else:
            conv_channels = []
            conv_kernel_sizes = []
            conv_strides = []
            poolings = []

        # Load batch data
        splice = 1
        num_stack = 1 if subsample or conv or encoder_type == 'cnn' else 2
        xs, ys, x_lens, y_lens = generate_data(
            model_type='attention',
            label_type=label_type,
            batch_size=2,
            num_stack=num_stack,
            splice=splice)

        if label_type == 'char':
            num_classes = 27
            map_fn = idx2char
        elif label_type == 'word':
            num_classes = 11
            map_fn = idx2word

        # Load model
        model = AttentionSeq2seq(
            input_size=xs.shape[-1] // splice // num_stack,  # 120
            encoder_type=encoder_type,
            encoder_bidirectional=bidirectional,
            encoder_num_units=256,
            encoder_num_proj=256 if projection else 0,
            encoder_num_layers=2,
            attention_type=attention_type,
            attention_dim=128,
            decoder_type=decoder_type,
            decoder_num_units=256,
            decoder_num_layers=2,
            embedding_dim=32,
            dropout_input=0.1,
            dropout_encoder=0.1,
            dropout_decoder=0.1,
            dropout_embedding=0.1,
            num_classes=num_classes,
            parameter_init_distribution='uniform',
            parameter_init=0.1,
            recurrent_weight_orthogonal=False,
            init_forget_gate_bias_with_one=True,
            subsample_list=[] if subsample is False else [True, False],
            subsample_type='concat' if subsample is False else subsample,
            init_dec_state=init_dec_state,
            sharpening_factor=1,
            logits_temperature=1,
            sigmoid_smoothing=False,
            coverage_weight=0,
            ctc_loss_weight=ctc_loss_weight,
            attention_conv_num_channels=10,
            attention_conv_width=201,
            num_stack=num_stack,
            splice=splice,
            conv_channels=conv_channels,
            conv_kernel_sizes=conv_kernel_sizes,
            conv_strides=conv_strides,
            poolings=poolings,
            batch_norm=batch_norm,
            scheduled_sampling_prob=0.1,
            scheduled_sampling_ramp_max_step=200,
            label_smoothing_prob=0.1 if label_smoothing else 0,
            weight_noise_std=1e-9,
            encoder_residual=residual,
            encoder_dense_residual=dense_residual,
            decoder_residual=residual,
            decoder_dense_residual=dense_residual)

        # Count total parameters
        for name in sorted(list(model.num_params_dict.keys())):
            num_params = model.num_params_dict[name]
            print("%s %d" % (name, num_params))
        print("Total %.3f M parameters" % (model.total_parameters / 1000000))

        # Define optimizer
        learning_rate = 1e-3
        model.set_optimizer('adam',
                            learning_rate_init=learning_rate,
                            weight_decay=1e-8,
                            lr_schedule=False,
                            factor=0.1,
                            patience_epoch=5)

        # Define learning rate controller
        lr_controller = Controller(learning_rate_init=learning_rate,
                                   backend='pytorch',
                                   decay_start_epoch=20,
                                   decay_rate=0.9,
                                   decay_patient_epoch=10,
                                   lower_better=True)

        # GPU setting
        model.set_cuda(deterministic=False, benchmark=True)

        # Train model
        max_step = 1000
        start_time_step = time.time()
        for step in range(max_step):

            # Step for parameter update
            model.optimizer.zero_grad()
            loss = model(xs, ys, x_lens, y_lens)
            loss.backward()
            nn.utils.clip_grad_norm(model.parameters(), 5)
            model.optimizer.step()

            # Inject Gaussian noise to all parameters
            if loss.data[0] < 50:
                model.weight_noise_injection = True

            if (step + 1) % 10 == 0:
                # Decode
                best_hyps, perm_idx = model.decode(
                    xs, x_lens,
                    # beam_width=1,
                    beam_width=2,
                    max_decode_len=60)

                # Compute accuracy
                if label_type == 'char':
                    str_true = map_fn(ys[0, :y_lens[0]][1:-1])
                    str_pred = map_fn(best_hyps[0][0:-1]).split('>')[0]
                    ler = compute_cer(ref=str_true.replace('_', ''),
                                      hyp=str_pred.replace('_', ''),
                                      normalize=True)
                elif label_type == 'word':
                    str_true = map_fn(ys[0, : y_lens[0]][1: -1])
                    str_pred = map_fn(best_hyps[0][0: -1]).split('>')[0]
                    ler = compute_wer(ref=str_true.split('_'),
                                      hyp=str_pred.split('_'),
                                      normalize=True)

                duration_step = time.time() - start_time_step
                print('Step %d: loss=%.3f / ler=%.3f / lr=%.5f (%.3f sec)' %
                      (step + 1, loss.data[0], ler, learning_rate, duration_step))
                start_time_step = time.time()

                # Visualize
                print('Ref: %s' % str_true)
                print('Hyp: %s' % str_pred)

                # Decode by theCTC decoder
                if model.ctc_loss_weight >= 0.1:
                    best_hyps_ctc, perm_idx = model.decode_ctc(
                        xs, x_lens, beam_width=1)
                    str_pred_ctc = map_fn(best_hyps_ctc[0])
                    print('Hyp (CTC): %s' % str_pred_ctc)

                if ler < 0.1:
                    print('Modle is Converged.')
                    break

                # Update learning rate
                model.optimizer, learning_rate = lr_controller.decay_lr(
                    optimizer=model.optimizer,
                    learning_rate=learning_rate,
                    epoch=step,
                    value=ler)


if __name__ == "__main__":
    unittest.main()
