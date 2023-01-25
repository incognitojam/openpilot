from cereal import car
from common.numpy_fast import clip
from opendbc.can.packer import CANPacker
from selfdrive.car import apply_std_curvature_limits
from selfdrive.car.ford.fordcan import create_acc_command, create_acc_ui_msg, create_button_msg, create_lat_ctl_msg, \
  create_lka_msg, create_lkas_ui_msg
from selfdrive.car.ford.values import CANBUS, CarControllerParams

VisualAlert = car.CarControl.HUDControl.VisualAlert


class CarController:
  def __init__(self, dbc_name, CP, VM):
    self.CP = CP
    self.CCP = CarControllerParams(CP)
    self.VM = VM
    self.packer = CANPacker(dbc_name)

    self.frame = 0
    self.main_on_last = False
    self.lkas_enabled_last = False
    self.steer_alert_last = False
    self.apply_curvature_last = 0.

  def update(self, CC, CS):
    can_sends = []

    actuators = CC.actuators
    hud_control = CC.hudControl

    main_on = CS.out.cruiseState.available
    steer_alert = hud_control.visualAlert in (VisualAlert.steerRequired, VisualAlert.ldw)

    ### acc buttons ###
    if CC.cruiseControl.cancel:
      can_sends.append(create_button_msg(self.packer, CS.buttons_stock_values, cancel=True))
      can_sends.append(create_button_msg(self.packer, CS.buttons_stock_values, cancel=True, bus=CANBUS.main))
    elif CC.cruiseControl.resume and (self.frame % self.CCP.BUTTONS_STEP) == 0:
      can_sends.append(create_button_msg(self.packer, CS.buttons_stock_values, resume=True))
      can_sends.append(create_button_msg(self.packer, CS.buttons_stock_values, resume=True, bus=CANBUS.main))
    # if stock lane centering isn't off, send a button press to toggle it off
    # the stock system checks for steering pressed, and eventually disengages cruise control
    elif CS.acc_tja_status_stock_values["Tja_D_Stat"] != 0 and (self.frame % self.CCP.ACC_UI_STEP) == 0:
      can_sends.append(create_button_msg(self.packer, CS.buttons_stock_values, tja_toggle=True))


    ### lateral control ###
    # send steering commands at 20Hz
    if (self.frame % self.CCP.STEER_STEP) == 0:
      if CC.latActive:
        # apply limits to curvature
        apply_curvature = apply_std_curvature_limits(actuators.curvature, self.apply_curvature_last, CS.out.vEgo,
                                                     self.CCP)
        # clip to signal range
        apply_curvature = clip(apply_curvature, -self.CCP.CURVATURE_MAX, self.CCP.CURVATURE_MAX)
      else:
        apply_curvature = 0.

      angle_steer_des = -self.VM.get_steer_from_curvature(apply_curvature, CS.out.vEgo, 0.0)

      # set slower ramp type when small steering angle change
      # 0=Slow, 1=Medium, 2=Fast, 3=Immediately
      steer_change = abs(CS.out.steeringAngleDeg - angle_steer_des)
      if steer_change < 2.5:
        ramp_type = 0
      elif steer_change < 5.0:
        ramp_type = 1
      elif steer_change < 7.5:
        ramp_type = 2
      else:
        ramp_type = 3
      precision = 1  # 0=Comfortable, 1=Precise (the stock system always uses comfortable)

      lca_rq = 1 if CC.latActive else 0
      can_sends.append(create_lka_msg(self.packer))
      can_sends.append(create_lat_ctl_msg(self.packer, lca_rq, ramp_type, precision, 0., 0., -apply_curvature, 0.))

      self.apply_curvature_last = apply_curvature


    ### longitudinal control ###
    # send acc command at 50Hz
    if self.CP.openpilotLongitudinalControl and (self.frame % self.CCP.ACC_CONTROL_STEP) == 0:
      accel = clip(actuators.accel, self.CCP.ACCEL_MIN, self.CCP.ACCEL_MAX)

      if accel > -0.5:
        prpl_a_rq = accel
        brk_decel_b_rq = 0
      else:
        prpl_a_rq = -5.0
        brk_decel_b_rq = 1

      brk_a_rq = accel
      brk_prchg_b_rq = 1 if accel < -0.1 else 0

      cmbb_enable = 1 if CC.longActive else 0

      can_sends.append(create_acc_command(self.packer, cmbb_enable, prpl_a_rq, brk_a_rq, brk_decel_b_rq, brk_prchg_b_rq))


    ### ui ###
    send_ui = (self.main_on_last != main_on) or (self.lkas_enabled_last != CC.latActive) or \
              (self.steer_alert_last != steer_alert)

    # send lkas ui command at 1Hz or if ui state changes
    if (self.frame % self.CCP.LKAS_UI_STEP) == 0 or send_ui:
      can_sends.append(create_lkas_ui_msg(self.packer, main_on, CC.latActive, steer_alert, hud_control,
                                          CS.lkas_status_stock_values))

    # send acc ui command at 20Hz or if ui state changes
    if (self.frame % self.CCP.ACC_UI_STEP) == 0 or send_ui:
      can_sends.append(create_acc_ui_msg(self.packer, main_on, CC.latActive, hud_control,
                                         CS.acc_tja_status_stock_values))

    self.main_on_last = main_on
    self.lkas_enabled_last = CC.latActive
    self.steer_alert_last = steer_alert

    new_actuators = actuators.copy()
    new_actuators.curvature = self.apply_curvature_last

    self.frame += 1
    return new_actuators, can_sends
