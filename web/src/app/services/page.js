'use client';

import React, {useState} from 'react';
import dayjs from 'dayjs';
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import {Menu} from "@/components/Menu/Menu";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import List from "@mui/material/List";
import {AdapterDayjs} from '@mui/x-date-pickers/AdapterDayjs';
import {LocalizationProvider} from '@mui/x-date-pickers/LocalizationProvider';
import {DateCalendar} from '@mui/x-date-pickers/DateCalendar';
import Chip from '@mui/material/Chip';
import {useStateContext} from "@/providers";

const hospitalList = ['Chelsea and Westminster Hospital', 'Kepier Hospital']
const availableTimeSlots = ['12:00', '13:00', '15:15']

const Make = ({ onSubmit }) => {
    const now = dayjs();
    const [selectedHospital, setSelectedHospital] = useState(null);
    const [selectedDate, setSelectedDate] = useState(null);
    const [selectedTime, setSelectedTime] = useState(null);

    return (
        <LocalizationProvider dateAdapter={AdapterDayjs}>
            <List
                component="div"
                sx={{width: '100%'}}
            >
                {hospitalList.map((hospital) => (
                    <ListItemButton
                        key={hospital}
                        selected={hospital === selectedHospital}
                        sx={{width: 'fit-content'}}
                        onClick={() => setSelectedHospital(hospital)}
                    >
                        <ListItemText primary={hospital}/>
                    </ListItemButton>
                ))}
            </List>
            {!!selectedHospital && (
                <>
                    <DateCalendar minDate={now} value={selectedDate} onChange={setSelectedDate} sx={{margin: 0}}/>
                    <List
                        component="div"
                        sx={{width: '100%', flexDirection: 'row', display: 'flex', gap: '4px'}}
                    >
                        {availableTimeSlots.map((time) => (
                            <Chip
                                key={time}
                                label={time}
                                size="medium"
                                color={time === selectedTime ? 'primary' : 'default'}
                                variant={time === selectedTime ? 'filled' : 'outlined'}
                                onClick={() => {
                                    setSelectedTime((prevState) => {
                                        if (prevState) {
                                            return null;
                                        }

                                        return time;
                                    });
                                }}
                            />
                        ))}
                    </List>
                    <Button
                        variant="contained"
                        disabled={!selectedDate || !selectedTime}
                        sx={{width: 'fit-content'}}
                        onClick={() => onSubmit(`${selectedHospital} ${selectedDate} ${selectedTime}`)}
                    >
                        Submit
                    </Button>
                </>
            )}
        </LocalizationProvider>
    )
}

const Cancel = ({ list, onDelete }) => {
    if (!list?.length) return null;

    return (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: '4px'}}>
            {list.map((item) => (
                <Chip
                    key={item}
                    label={item}
                    size="medium"
                    onDelete={() => onDelete(item)}
                    variant="filled"
                />
            ))}
        </Box>
    )
}

const Actions = () => {
    const { appointmentList, setAppointmentList } = useStateContext();
    const [screen, setScreen] = useState('main');

    return (
        <Box sx={{display: 'flex', flexDirection: 'column', gap: '8px'}}>
            <Box sx={{display: 'flex', gap: '4px'}}>
                <Button
                    variant="contained"
                    color="primary"
                    onClick={() => setScreen((prevState) => {
                        if (prevState === 'make') {
                            return 'main';
                        }

                        return 'make';
                    })
                }>
                    Make an appointment
                </Button>
                <Button
                    variant="contained"
                    color="secondary"
                    onClick={() => setScreen((prevState) => {
                        if (prevState === 'cancel') {
                            return 'main';
                        }

                        return 'cancel';
                    })}
                >
                    Cancel an appointment
                </Button>
            </Box>
            {screen === 'make' && (
                <Make
                    onSubmit={(item) => {
                        setScreen('main');
                        setAppointmentList((prevState) => ([...prevState, item]))
                    }}
                />)}
            {screen === 'cancel' && (
                <Cancel
                    list={appointmentList}
                    onDelete={(item) => {
                        setAppointmentList((prevState) => prevState.filter((filtered) => item !== filtered))
                    }}
                />
            )}
        </Box>
    )
}

const Services = () => {
    const [isNhsActive, setNhsActive] = useState(false);

    return (
        <Box sx={{display: 'flex', width: '100%', height: '100%'}}>
            <Menu currentPage="services"/>
            <Box sx={{flexGrow: 1, position: 'relative', padding: 4}}>
                <img alt="union jack"
                     src="https://upload.wikimedia.org/wikipedia/commons/thumb/a/a5/Flag_of_the_United_Kingdom_%281-2%29.svg/1200px-Flag_of_the_United_Kingdom_%281-2%29.svg.png"
                     style={{
                         position: 'absolute',
                         width: '100%',
                         inset: 0,
                         objectFit: 'cover',
                         objectPosition: 'center',
                         opacity: '0.3'
                     }}
                />
                {isNhsActive ? (
                    <Box sx={{display: 'flex', flexDirection: 'column', gap: '16px'}}>
                        <Actions/>
                        <Button onClick={() => setNhsActive(false)} sx={{width: 'fit-content'}}>
                            return
                        </Button>
                    </Box>
                ) : (
                    <Box sx={{display: 'flex', gap: '4px'}}>
                        <Button
                            variant="contained"
                            onClick={() => setNhsActive(true)}
                        >
                            NHS
                        </Button>
                        <Button
                            variant="contained"
                            disabled
                        >
                            HMRC
                        </Button>
                        <Button
                            variant="contained"
                            disabled
                        >
                            Home Office
                        </Button>
                    </Box>
                )}
            </Box>
        </Box>
    );
}

export default Services;
